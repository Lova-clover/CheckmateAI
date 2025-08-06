from flask import Flask, request, jsonify, g
import chess
import chess.engine
from flask_cors import CORS
import random
import os
import sqlite3
import math
import requests
import firebase_admin
from firebase_admin import credentials, firestore
import json

# 환경변수에서 JSON 문자열 불러오기
firebase_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

# 문자열을 딕셔너리로 변환
firebase_dict = json.loads(firebase_json)

# 인증 초기화
cred = credentials.Certificate(firebase_dict)
firebase_admin.initialize_app(cred)
firestore_db = firestore.client()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://checkmateai-app.vercel.app"}}, supports_credentials=True)

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://checkmateai-app.vercel.app'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

DB_PATH = os.path.join(os.path.dirname(__file__), "puzzles.db")
DB_URL = "https://www.dropbox.com/scl/fi/qu3izfif8iltdqvotqdpr/puzzles.db?rlkey=hkbt8zu0l28qj22o9rcitqidj&st=vo5edowl&dl=1" 

# ✅ 파일이 없을 경우 Dropbox에서 다운로드
if not os.path.exists(DB_PATH):
    print("📦 puzzles.db not found, downloading from Dropbox...")
    r = requests.get(DB_URL, stream=True)
    with open(DB_PATH, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish", "stockfish-linux-x86-64-avx2")
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
    return g.db

@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route("/ai/puzzle", methods=["GET"])
def get_puzzle():
    user_id = request.args.get("user_id")
    db = get_db()
    cursor = db.cursor()

    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict()["score"] if user_doc.exists else 1200

    lower = max(600, score - 100)
    upper = min(2400, score + 100)

    # 해당 난이도 구간 퍼즐 개수 먼저 가져옴
    cursor.execute("SELECT COUNT(*) FROM puzzles WHERE rating BETWEEN ? AND ?", (lower, upper))
    count = cursor.fetchone()[0]

    if count == 0:
        return jsonify({"error": "No puzzles found"}), 404

    # 무작위 오프셋 생성 (속도 매우 빠름)
    offset = random.randint(0, max(0, count - 1))

    # 단 하나의 퍼즐만 가져오기 (ORDER BY 제거로 속도 향상)
    cursor.execute("""
        SELECT fen, moves, rating, themes, puzzle_id
        FROM puzzles
        WHERE rating BETWEEN ? AND ?
        LIMIT 1 OFFSET ?
    """, (lower, upper, offset))

    puzzle = cursor.fetchone()
    
    board = chess.Board(puzzle[0])
    uci_solution = puzzle[1].split()

    return jsonify({
        "fen": puzzle[0],
        "solution": uci_solution,
        "description": f"난이도 {puzzle[2]}",
        "hint": uci_solution[0],
        "puzzle_id": puzzle[4],
        "score": score
    })
    
@app.route('/ai/move', methods=['POST', 'OPTIONS'])  # ✅ OPTIONS 추가
def ai_move():
    if request.method == 'OPTIONS':  # ✅ Preflight 처리
        return '', 200

    data = request.get_json()
    fen = data.get('fen')
    level = data.get('level', 'medium')

    if fen == "startpos":
        fen = chess.STARTING_FEN

    board = chess.Board(fen)

    try:
        if level == 'easy':
            if random.random() < 0.9:
                move = random.choice(list(board.legal_moves))
            else:
                result = engine.play(board, chess.engine.Limit(depth=1, time=0.3))
                move = result.move
        elif level == 'medium':
            if random.random() < 0.6:
                result = engine.play(board, chess.engine.Limit(depth=2, time=0.5))
                move = result.move
            else:
                info = engine.analyse(board, chess.engine.Limit(depth=2, time=1.0), multipv=3)
                candidates = [entry["pv"][0] for entry in info if "pv" in entry]
                if candidates:
                    move = random.choice(candidates)
                else:
                    result = engine.play(board, chess.engine.Limit(depth=2))
                    move = result.move
        else:
            result = engine.play(board, chess.engine.Limit(depth=4))
            move = result.move

        return jsonify({'move': move.uci()})
    except Exception as e:
        print("🔥 AI 서버 오류:", e)
        return jsonify({'error': str(e)}), 500

@app.route("/ai/puzzle/submit", methods=["POST"])
def submit_result():
    data = request.get_json()
    user_id = data["user_id"]
    puzzle_id = data["puzzle_id"]
    solved = data["solved"]
    time_taken = data["time"]

    # 퍼즐 난이도 (sqlite에서 가져옴)
    db_sqlite = get_db()
    cursor = db_sqlite.cursor()
    cursor.execute("SELECT rating FROM puzzles WHERE puzzle_id = ?", (puzzle_id,))
    puzzle_rating = cursor.fetchone()[0]

    # Firestore에서 유저 점수 불러오기
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict()["score"] if user_doc.exists else 1200

    # 점수 계산
    diff = puzzle_rating - score
    delta = 20 + diff // 40 if solved else -15 + diff // 80
    new_score = max(600, score + delta)

    # 점수 및 기록 저장
    user_ref.set({"score": new_score}, merge=True)
    user_ref.collection("records").add({
        "puzzle_id": puzzle_id,
        "solved": solved,
        "time": time_taken,
        "timestamp": firestore.SERVER_TIMESTAMP
    })

    return jsonify({"new_score": new_score, "delta": delta})

@app.route("/ai/user/stats", methods=["GET"])
def user_stats():
    user_id = request.args.get("user_id")
    user_ref = firestore_db.collection("users").document(user_id)
    user_doc = user_ref.get()
    score = user_doc.to_dict()["score"] if user_doc.exists else 1200

    # 전체 기록 가져와서 전체 통계 계산
    all_records = list(user_ref.collection("records").stream())
    total = len(all_records)
    success = sum(1 for r in all_records if r.to_dict().get("solved"))
    rate = round(success / total * 100, 1) if total > 0 else 0.0

    # 최근 5개만 별도로 가져오기
    records_ref = user_ref.collection("records") \
        .order_by("timestamp", direction=firestore.Query.DESCENDING) \
        .limit(5)
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

    return jsonify({
        "score": score,
        "total": total,
        "success": success,
        "success_rate": rate,
        "recent": recent
    })