import sqlite3

db_path = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# ExecutionLog 테이블 구조 확인
print("=== ExecutionLog Schema ===")
cursor.execute("PRAGMA table_info(ExecutionLog);")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# ExecutionSession 테이블 구조 확인
print("\n=== ExecutionSession Schema ===")
cursor.execute("PRAGMA table_info(ExecutionSession);")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# ExecutionMetric 테이블 구조 확인
print("\n=== ExecutionMetric Schema ===")
cursor.execute("PRAGMA table_info(ExecutionMetric);")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]}: {col[2]}")

# 각 테이블의 샘플 데이터 확인
print("\n=== ExecutionLog Sample (최근 3개) ===")
cursor.execute("SELECT id, agentId, level, type, createdAt FROM ExecutionLog ORDER BY createdAt DESC LIMIT 3;")
logs = cursor.fetchall()
for log in logs:
    print(f"  {log}")

print("\n=== ExecutionSession Sample ===")
cursor.execute("SELECT id, userId, name, status, createdAt FROM ExecutionSession ORDER BY createdAt DESC LIMIT 3;")
sessions = cursor.fetchall()
for session in sessions:
    print(f"  {session}")
