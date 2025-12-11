from ai_engine.puzzle_generator import PuzzleGenerator
import chess

pg = PuzzleGenerator()
puzzle = pg.get_random_puzzle('easy')

print(f"퍼즐 ID: {puzzle['puzzle_id']}")
print(f"FEN: {puzzle['fen']}")
print(f"해답: {puzzle['solution']}")
print(f"레이팅: {puzzle['rating']}")
print(f"테마: {puzzle['theme']}")

# 보드 상태 확인
board = chess.Board(puzzle['fen'])
print(f"\n현재 차례: {'백' if board.turn == chess.WHITE else '흑'}")
print(f"해답 첫 번째 수: {puzzle['solution'][0]}")

# 첫 번째 수를 SAN으로 변환
first_move = chess.Move.from_uci(puzzle['solution'][0])
first_move_san = board.san(first_move)
print(f"첫 번째 수 (SAN): {first_move_san}")

# 첫 번째 수를 둔 후
board.push(first_move)
print(f"\n첫 번째 수를 둔 후 차례: {'백' if board.turn == chess.WHITE else '흑'}")
print(f"두 번째 수: {puzzle['solution'][1] if len(puzzle['solution']) > 1 else 'N/A'}")
