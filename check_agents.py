import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
cur = db.cursor()
admin_id = '63eac2de-bf58-4e5a-b146-8eaf6c96f98c'
cur.execute("SELECT id, slug FROM AgentProfile WHERE userId = ? LIMIT 5", (admin_id,))
rows = cur.fetchall()
print(f"Admin owns {len(rows)} agents (showing 5):")
for r in rows:
    print(f"  {r[0]} - {r[1]}")

# Also get total count
cur.execute("SELECT COUNT(*) FROM AgentProfile WHERE userId = ?", (admin_id,))
total = cur.fetchone()[0]
print(f"Total: {total}")
db.close()
