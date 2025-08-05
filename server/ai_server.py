from flask import Flask, request, jsonify, g
import chess
import chess.engine
from flask_cors import CORS
import random
import os
import sqlite3
import math
import requests

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

def ensure_indexes():
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_rating ON puzzles(rating)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_puzzle_id ON puzzles(puzzle_id)")
    db.commit()
    db.close()

ensure_indexes()

def ensure_tables():
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            user_id TEXT PRIMARY KEY,
            score INTEGER DEFAULT 1200
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS puzzle_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            puzzle_id TEXT,
            solved BOOLEAN,
            time_taken INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    db.close()

def ensure_columns():
    db = sqlite3.connect(DB_PATH)
    cursor = db.cursor()
    try:
        cursor.execute("ALTER TABLE puzzle_results ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")
        print("✅ created_at 컬럼 추가됨")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ created_at 컬럼은 이미 존재함")
        else:
            raise e
    db.commit()
    db.close()
    
ensure_indexes()
ensure_tables()

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

    cursor.execute("SELECT score FROM user_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    score = row[0] if row else 1200

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
    
@app.route("/ai/puzzle/submit", methods=["POST"])
def submit_result():
    data = request.get_json()
    user_id = data["user_id"]
    puzzle_id = data["puzzle_id"]
    solved = data["solved"]
    time_taken = data["time"]

    db = get_db()
    cursor = db.cursor()

    # 퍼즐 난이도 가져오기
    cursor.execute("SELECT rating FROM puzzles WHERE puzzle_id = ?", (puzzle_id,))
    puzzle_rating = cursor.fetchone()[0]

    # 유저 점수 가져오기
    cursor.execute("SELECT score FROM user_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    user_score = row[0] if row else 1200

    # 점수 차이 기반 업데이트
    diff = puzzle_rating - user_score
    delta = 20 + diff // 40 if solved else -15 + diff // 80
    new_score = max(600, user_score + delta)

    # 저장
    cursor.execute("""
        INSERT INTO puzzle_results (user_id, puzzle_id, solved, time_taken)
        VALUES (?, ?, ?, ?)
    """, (user_id, puzzle_id, solved, time_taken))

    cursor.execute("""
        INSERT OR REPLACE INTO user_profile (user_id, score)
        VALUES (?, ?)
    """, (user_id, new_score))

    db.commit()
    return jsonify({"new_score": new_score, "delta": delta})

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

@app.route("/ai/user/stats", methods=["GET"])
def user_stats():
    user_id = request.args.get("user_id")
    db = get_db()
    cursor = db.cursor()

    # 점수
    cursor.execute("SELECT score FROM user_profile WHERE user_id = ?", (user_id,))
    score = cursor.fetchone()[0]

    # 퍼즐 통계
    cursor.execute("SELECT COUNT(*), SUM(CASE WHEN solved THEN 1 ELSE 0 END) FROM puzzle_results WHERE user_id = ?", (user_id,))
    total, success = cursor.fetchone()
    success_rate = (success or 0) / total * 100 if total > 0 else 0

    # 최근 5개 결과
    cursor.execute("""
        SELECT puzzle_id, solved, time_taken, created_at
        FROM puzzle_results
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 5
    """, (user_id,))
    recent = cursor.fetchall()

    return jsonify({
        "score": score,
        "total": total,
        "success": success or 0,
        "success_rate": round(success_rate, 1),
        "recent": [
            {"puzzle_id": r[0], "solved": bool(r[1]), "time": r[2], "date": r[3]}
            for r in recent
        ]
    })