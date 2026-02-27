import sqlite3

db_path = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 모든 테이블 목록
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()

print("=== All Tables ===")
for table in tables:
    print(f"  {table[0]}")

# execution/history와 관련된 테이블 찾기
execution_tables = [t[0] for t in tables if 'exec' in t[0].lower() or 'history' in t[0].lower() or 'log' in t[0].lower()]
print(f"\n=== Execution/History Related Tables ===")
for table in execution_tables:
    print(f"  {table}")
    # 각 테이블의 행 수 출력
    cursor.execute(f"SELECT COUNT(*) FROM {table};")
    count = cursor.fetchone()[0]
    print(f"    → {count} rows")

conn.close()
