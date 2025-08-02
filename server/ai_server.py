from flask import Flask, request, jsonify
import chess
import chess.engine
from flask_cors import CORS
import random

app = Flask(__name__)
CORS(app)

STOCKFISH_PATH = "C:/CheckmateAI/server/stockfish/stockfish-windows-x86-64-avx2.exe"
engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)

@app.route('/ai/puzzle', methods=['GET'])
def get_puzzle():
    def generate_mate_puzzle(n):
        board = chess.Board()
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            for _ in range(random.randint(8, 14)):
                if board.is_game_over():
                    return None
                move = engine.play(board, chess.engine.Limit(depth=2)).move
                board.push(move)

            start_fen = board.fen()
            info = engine.analyse(board, chess.engine.Limit(depth=12), multipv=1)

            if "score" in info and info["score"].is_mate():
                mate_score = info["score"].mate()
                if mate_score and abs(mate_score) == n:
                    tmp_board = chess.Board(start_fen)
                    solution = []
                    for _ in range(n):
                        if tmp_board.is_game_over():
                            break
                        move = engine.play(tmp_board, chess.engine.Limit(depth=5)).move
                        solution.append(tmp_board.san(move))
                        tmp_board.push(move)

                    if len(solution) == n:
                        piece = chess.Board(start_fen).piece_at(move.from_square)
                        return {
                            'fen': start_fen,
                            'solution': solution,
                            'hint': f"{piece.symbol().upper()} 시작" if piece else '?',
                            'description': f"Mate in {n}"
                        }
        return None

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
        puzzle_type = random.choice(['mate', 'normal'])
        if puzzle_type == 'mate':
            n = random.choice([2, 3])
            puzzle = generate_mate_puzzle(n)
        else:
            puzzle = generate_normal_puzzle()

        if puzzle:
            return jsonify(puzzle)

    return jsonify({'error': '퍼즐 생성 실패'}), 500


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