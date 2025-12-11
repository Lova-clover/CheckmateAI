from ai_engine.puzzle_generator import PuzzleGenerator
import time

pg = PuzzleGenerator()

print("\n퍼즐 로딩 속도 테스트 (10회)...")
print("-" * 50)

times = []
for i in range(10):
    start = time.time()
    puzzle = pg.get_random_puzzle('medium')
    end = time.time()
    elapsed = (end - start) * 1000
    times.append(elapsed)
    print(f"{i+1}. {puzzle['puzzle_id']} - {elapsed:.2f}ms")

avg_time = sum(times) / len(times)
min_time = min(times)
max_time = max(times)

print("-" * 50)
print(f"평균: {avg_time:.2f}ms")
print(f"최소: {min_time:.2f}ms")
print(f"최대: {max_time:.2f}ms")
