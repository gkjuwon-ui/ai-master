import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
print("Tables:", tables)

# Find agent table columns
for t in tables:
    if 'agent' in t.lower() or 'llm' in t.lower():
        cols = [r[1] for r in db.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n{t}: {cols}")

db.close()
