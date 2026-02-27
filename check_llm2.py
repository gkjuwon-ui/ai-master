import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
db.row_factory = sqlite3.Row

# Check LLM configs used by agents
rows = db.execute("""
    SELECT a.name, l.provider, l.model, l.baseUrl
    FROM Agent a 
    JOIN LLMConfig l ON l.id = a.llmConfigId
    WHERE a.name IN ('TrendSpy', 'Taskmaster', 'NoteGrab', 'Sentinel Watch', 'Scribe')
""").fetchall()
for r in rows:
    print(f"{r['name']}: provider={r['provider']} model={r['model']} baseUrl={r['baseUrl']}")

# Also check unique LLM configs
print("\n--- All unique LLM configs ---")
configs = db.execute("SELECT id, provider, model, baseUrl, isDefault FROM LLMConfig").fetchall()
for c in configs:
    print(f"id={c['id'][:8]}... provider={c['provider']} model={c['model']} baseUrl={c['baseUrl']} default={c['isDefault']}")

db.close()
