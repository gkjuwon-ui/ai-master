import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
db.row_factory = sqlite3.Row

# Check which agents have llmConfigId set
rows = db.execute("""
    SELECT name, llmConfigId FROM Agent 
    WHERE name IN ('TrendSpy', 'Taskmaster', 'NoteGrab', 'Sentinel Watch', 'Scribe')
""").fetchall()
for r in rows:
    print(f"{r['name']}: llmConfigId={r['llmConfigId']}")

# Check the single LLM config details
config = db.execute("SELECT * FROM LLMConfig LIMIT 1").fetchone()
if config:
    keys = config.keys()
    for k in keys:
        v = config[k]
        if k == 'apiKey' and v and len(v) > 12:
            v = v[:8] + '...' + v[-4:]
        print(f"  {k}={v}")

db.close()
