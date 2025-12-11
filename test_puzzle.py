from ai_engine.puzzle_generator import PuzzleGenerator

pg = PuzzleGenerator()
puzzle = pg.get_random_puzzle('easy')

print(f"퍼즐 ID: {puzzle['puzzle_id']}")
print(f"레이팅: {puzzle['rating']}")
print(f"테마: {puzzle['theme']}")
print(f"FEN: {puzzle['fen']}")
print(f"해답 길이: {len(puzzle['solution'])}수")
print(f"첫 번째 수: {puzzle['solution'][0]}")
