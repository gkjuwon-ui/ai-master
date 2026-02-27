import sqlite3

db = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db)
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in c.fetchall()]
print('Tables:', tables)
for t in tables:
    c.execute(f'SELECT COUNT(*) FROM "{t}"')
    print(f'  {t}: {c.fetchone()[0]} rows')
conn.close()
