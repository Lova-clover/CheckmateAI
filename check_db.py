import sqlite3

conn = sqlite3.connect('puzzles.db')
cursor = conn.cursor()

# 테이블 확인
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("테이블:", [row[0] for row in cursor.fetchall()])

# 퍼즐 테이블 구조 확인
cursor.execute("PRAGMA table_info(puzzles)")
print("\n컬럼 정보:")
for row in cursor.fetchall():
    print(f"  {row[1]} ({row[2]})")

# 샘플 데이터
cursor.execute("SELECT * FROM puzzles LIMIT 1")
cols = [desc[0] for desc in cursor.description]
print(f"\n컬럼명: {cols}")
print(f"샘플 데이터: {cursor.fetchone()}")

# 전체 개수
cursor.execute("SELECT COUNT(*) FROM puzzles")
print(f"\n총 퍼즐 개수: {cursor.fetchone()[0]:,}")

conn.close()
