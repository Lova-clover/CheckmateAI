import os
import sqlite3
import chess
import chess.engine
import firebase_admin
from firebase_admin import credentials, firestore
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import requests
import json

# --- Firebase Admin SDK 초기화 ---
# 환경 변수에서 Firebase 인증 정보 로드
firebase_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
if not firebase_json_str:
    raise ValueError("FIREBASE_SERVICE_ACCOUNT 환경 변수가 설정되지 않았습니다.")

firebase_credentials = json.loads(firebase_json_str)
cred = credentials.Certificate(firebase_credentials)
firebase_admin.initialize_app(cred)
firestore_db = firestore.client()

# --- FastAPI 앱 생성 및 CORS 설정 ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # Vercel에 배포된 React 앱의 주소를 허용합니다.
    allow_origins=["https://checkmateai-app.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Stockfish 엔진 및 DB 설정 ---
DB_PATH = os.path.join(os.path.dirname(__file__), "puzzles.db")

# DB 파일이 없으면 다운로드
if not os.path.exists(DB_PATH):
    print("puzzles.db를 찾을 수 없어 다운로드합니다...")
    db_url = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1"
    r = requests.get(db_url, stream=True)
    r.raise_for_status()
    with open(DB_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish", "stockfish-linux-x86-64-avx2")
# 앱 시작 시 엔진을 한 번만 로드합니다.
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

def get_db_conn():
    return sqlite3.connect(DB_PATH)

# --- API 요청/응답 모델 정의 ---
class MoveRequest(BaseModel):
    fen: str
    level: str = 'medium'

class PuzzleSubmitRequest(BaseModel):
    user_id: str
    puzzle_id: str
    solved: bool
    time: int

# --- API 엔드포인트 ---
@app.post("/ai/move")
async def ai_move(request: MoveRequest):
    board = chess.Board(request.fen)
    try:
        # 비동기로 엔진을 실행하여 응답 지연을 최소화합니다.
        result = await engine.play(board, chess.engine.Limit(time=0.5))
        return {"move": result.move.uci()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/ai/puzzle")
def get_puzzle(user_id: str):
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict().get("score", 1200) if user_doc.exists else 1200

    conn = get_db_conn()
    cursor = conn.cursor()
    # 로직은 기존과 동일하게 유지
    cursor.execute("SELECT puzzle_id, fen, moves, rating FROM puzzles WHERE rating BETWEEN ? AND ? ORDER BY RANDOM() LIMIT 1", (score - 100, score + 100))
    puzzle = cursor.fetchone()
    conn.close()

    if not puzzle:
        raise HTTPException(status_code=404, detail="No puzzles found in the rating range.")

    return {
        "puzzle_id": puzzle[0],
        "fen": puzzle[1],
        "solution": puzzle[2].split(),
        "description": f"난이도 {puzzle[3]}",
        "hint": puzzle[2].split()[0],
        "score": score
    }

@app.post("/ai/puzzle/submit")
def submit_puzzle(request: PuzzleSubmitRequest):
    # 기존 점수 계산 및 Firestore 저장 로직을 그대로 사용합니다.
    # (이 부분은 ai_server.py의 submit_result 함수와 거의 동일합니다)
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT rating FROM puzzles WHERE puzzle_id = ?", (request.puzzle_id,))
    puzzle_rating_row = cursor.fetchone()
    conn.close()
    if not puzzle_rating_row:
        raise HTTPException(status_code=404, detail="Puzzle not found.")
    puzzle_rating = puzzle_rating_row[0]

    user_ref = firestore_db.collection("users").document(request.user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict().get("score", 1200) if user_doc.exists else 1200

    diff = puzzle_rating - score
    delta = 20 + diff // 40 if request.solved else -15 + diff // 80
    new_score = max(600, score + delta)

    user_ref.set({"score": new_score}, merge=True)
    user_ref.collection("records").add({
        "puzzle_id": request.puzzle_id,
        "solved": request.solved,
        "time": request.time,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return {"new_score": new_score, "delta": delta}


@app.get("/ai/user/stats")
def get_user_stats(user_id: str):
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict()["score"] if user_doc.exists else 1200

    all_records = list(user_ref.collection("records").stream())
    total = len(all_records)
    success = sum(1 for r in all_records if r.to_dict().get("solved"))
    rate = round(success / total * 100, 1) if total > 0 else 0.0

    records_ref = user_ref.collection("records").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5)
    recent_records = records_ref.stream()
    recent = []
    for r in recent_records:
        data = r.to_dict()
        recent.append({
            "puzzle_id": data.get("puzzle_id"),
            "solved": data.get("solved"),
            "time": data.get("time"),
            "date": data.get("timestamp").isoformat() if data.get("timestamp") else None
        })
    return {
        "score": score,
        "total": total,
        "success": success,
        "success_rate": rate,
        "recent": recent
    }

@app.on_event("shutdown")
def shutdown_event():
    engine.quit()