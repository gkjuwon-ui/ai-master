import sqlite3

db_path = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("Clearing execution history...")

# ExecutionLog 삭제
cursor.execute("DELETE FROM ExecutionLog;")
deleted_logs = cursor.rowcount
print(f"✓ Deleted {deleted_logs} ExecutionLog entries")

# ExecutionMetric 삭제
cursor.execute("DELETE FROM ExecutionMetric;")
deleted_metrics = cursor.rowcount
print(f"✓ Deleted {deleted_metrics} ExecutionMetric entries")

# ExecutionSession 삭제
cursor.execute("DELETE FROM ExecutionSession;")
deleted_sessions = cursor.rowcount
print(f"✓ Deleted {deleted_sessions} ExecutionSession entries")

conn.commit()
print("\n✅ Execution history cleared successfully!")

conn.close()
