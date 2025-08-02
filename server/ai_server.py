from flask import Flask, request, jsonify
import chess
import chess.engine
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

STOCKFISH_PATH = "C:/CheckmateAI/server/stockfish/stockfish-windows-x86-64-avx2.exe"
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = 'https://checkmateai-app.vercel.app'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

@app.route('/ai/puzzle', methods=['GET', 'OPTIONS'])  # ✅ OPTIONS 추가
def get_puzzle():
    if request.method == 'OPTIONS':  # ✅ Preflight 요청 처리
        return '', 200

    def generate_mate_puzzle(n):
        board = chess.Board()
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            for _ in range(random.randint(10, 16)):
                if board.is_game_over():
                    return None
                board.push(engine.play(board, chess.engine.Limit(depth=2)).move)

            non_king_pieces = [p for p in board.piece_map().values() if p.symbol().lower() != 'k']
            if len(non_king_pieces) < 6:
                return None

            start_fen = board.fen()

            prev_info = engine.analyse(board, chess.engine.Limit(depth=8))
            prev_score = prev_info["score"].white().score(mate_score=10000)
            if prev_score is None or prev_score < -200:
                return None

            result = engine.play(board, chess.engine.Limit(depth=5))
            best_move = result.move
            board.push(best_move)

            info = engine.analyse(board, chess.engine.Limit(depth=12))
            if not info["score"].is_mate() or abs(info["score"].mate()) != n - 1:
                return None

            board = chess.Board(start_fen)
            legal_moves = list(board.legal_moves)
            mate_alternatives = 0
            for move in legal_moves:
                if move != best_move:
                    board.push(move)
                    alt_info = engine.analyse(board, chess.engine.Limit(depth=6))
                    if alt_info["score"].is_mate():
                        mate_alternatives += 1
                    board.pop()

            if mate_alternatives > 0:
                return None

            tmp_board = chess.Board(start_fen)
            piece_before = tmp_board.piece_at(best_move.from_square)
            tmp_board.push(best_move)
            captured_piece = tmp_board.piece_at(best_move.to_square)
            was_sacrifice = (
                piece_before and piece_before.symbol().lower() == 'q' and captured_piece is None
            )

            tmp_board = chess.Board(start_fen)
            solution = []
            for _ in range(n):
                if tmp_board.is_game_over():
                    break
                move = engine.play(tmp_board, chess.engine.Limit(depth=6)).move
                solution.append(tmp_board.san(move))
                tmp_board.push(move)

            if len(solution) != n:
                return None

            hint = f"{piece_before.symbol().upper()} 시작" if piece_before else '?'
            description = f"Mate in {n}" + (" (Q-sac!)" if was_sacrifice and random.random() < 0.7 else "")

            return {
                'fen': start_fen,
                'solution': solution,
                'hint': hint,
                'description': description
            }

    def generate_normal_puzzle():
        board = chess.Board()
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            for _ in range(random.randint(6, 12)):
                if board.is_game_over():
                    return None
                board.push(engine.play(board, chess.engine.Limit(depth=2)).move)

            start_fen = board.fen()
            solution = []
            last_move = None

            for _ in range(3):
                if board.is_game_over():
                    break
                result = engine.play(board, chess.engine.Limit(depth=6))
                move = result.move
                solution.append(board.san(move))
                board.push(move)
                last_move = move

            if len(solution) < 2 or not last_move:
                return None

            board_for_hint = chess.Board(start_fen)
            try:
                first_move = board_for_hint.parse_san(solution[0])
                piece = board_for_hint.piece_at(first_move.from_square)
                hint = f"{piece.symbol().upper()} 시작" if piece else '?'
            except:
                hint = '?'

            return {
                'fen': start_fen,
                'solution': solution,
                'hint': hint,
                'description': "최선의 수를 찾아보세요"
            }

    max_attempts = 10
    for _ in range(max_attempts):
        puzzle_type = 'mate' if random.random() < 0.8 else 'normal'
        if puzzle_type == 'mate':
            n = random.choice([2, 3])
            puzzle = generate_mate_puzzle(n)
        else:
            puzzle = generate_normal_puzzle()

        if puzzle:
            return jsonify(puzzle)

    fallback = {
        'fen': "rnb1kbnr/pppp1ppp/8/4p3/8/2P5/PPP1PPPP/RNBQKBNR w KQkq - 0 3",
        'solution': ["d4", "exd5", "Qxd4", "Nc6", "Qxg7#"],
        'hint': "Q 시작",
        'description': "Mate in 3 (예시 퍼즐)"
    }
    return jsonify(fallback), 200

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

if __name__ == '__main__':
    app.run(port=5000)
