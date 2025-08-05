from flask import Flask, request, jsonify
import chess
import chess.engine
from flask_cors import CORS
import random
import os
import sqlite3

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "https://checkmateai-app.vercel.app"}})

DB_PATH = os.path.join(os.path.dirname(__file__), "puzzles.db")
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "stockfish", "stockfish-linux-x86-64-avx2")
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

@app.route("/ai/puzzle", methods=["GET"])
def get_puzzle():
    user_id = request.args.get("user_id")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 사용자 점수 가져오기
    cursor.execute("SELECT score FROM user_profile WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    score = row[0] if row else 1200

    # 추천 퍼즐 (±100)
    lower = max(600, score - 100)
    upper = min(2400, score + 100)
    cursor.execute("""
        SELECT fen, moves, rating, themes, puzzle_id
        FROM puzzles
        WHERE rating BETWEEN ? AND ?
        ORDER BY RANDOM()
        LIMIT 1
    """, (lower, upper))

    puzzle = cursor.fetchone()
    conn.close()

    return jsonify({
        "fen": puzzle[0],
        "solution": puzzle[1].split(),
        "description": f"난이도 {puzzle[2]}",
        "hint": puzzle[1].split()[0],
        "puzzle_id": puzzle[4],
    })

@app.route("/ai/puzzle/submit", methods=["POST"])
def submit_result():
    data = request.get_json()
    user_id = data["user_id"]
    puzzle_id = data["puzzle_id"]
    solved = data["solved"]
    time_taken = data["time"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    conn.commit()
    conn.close()

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
                result = engine.play(board, chess.engine.Limit(depth=1))
                move = result.move
        elif level == 'medium':
            if random.random() < 0.6:
                result = engine.play(board, chess.engine.Limit(depth=2))
                move = result.move
            else:
                info = engine.analyse(board, chess.engine.Limit(depth=2), multipv=3)
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

