from flask import Flask, request, jsonify
import chess
import chess.engine
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

STOCKFISH_PATH = "C:/CheckmateAI/server/stockfish/stockfish-windows-x86-64-avx2.exe"
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

@app.route('/ai/move', methods=['POST'])
def ai_move():
    data = request.get_json()
    fen = data.get('fen')
    level = data.get('level', 'medium')

    if fen == "startpos":
        fen = chess.STARTING_FEN

    board = chess.Board(fen)

    try:
        if level == 'easy':
            # 완전 초보 수준: 90% 랜덤수, 10% depth=1
            if random.random() < 0.9:
                move = random.choice(list(board.legal_moves))
            else:
                result = engine.play(board, chess.engine.Limit(depth=1))
                move = result.move

        elif level == 'medium':
            # 초보 ~ 중급자 수준: 60% depth=2, 40% top 3 수 중 무작위
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

        else:  # hard
            # depth=4 또는 0.5초 제한
            result = engine.play(board, chess.engine.Limit(depth=4))
            move = result.move

        return jsonify({'move': move.uci()})
    except Exception as e:
        print("🔥 AI 서버 오류:", e)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(port=5000)