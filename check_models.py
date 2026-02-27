import sqlite3, json

conn = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = conn.cursor()

# List tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)

# Find Agent table
for t in tables:
    if 'agent' in t.lower():
        print(f"\n=== {t} columns ===")
        c.execute(f"PRAGMA table_info({t})")
        cols = c.fetchall()
        for col in cols:
            print(f"  {col[1]} ({col[2]})")

# Try to get model info
for t in tables:
    if 'agent' in t.lower() and 'agent' == t.lower()[:5]:
        try:
            c.execute(f"SELECT name, llm_config FROM {t} LIMIT 5")
            for row in c.fetchall():
                name = row[0]
                cfg = row[1]
                if cfg:
                    try:
                        d = json.loads(cfg) if isinstance(cfg, str) else cfg
                        model = d.get('model', '?')
                        print(f"  {name}: model={model}")
                    except:
                        print(f"  {name}: raw={str(cfg)[:100]}")
        except Exception as e:
            print(f"  Error querying {t}: {e}")

conn.close()
