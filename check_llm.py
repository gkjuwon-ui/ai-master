import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
db.row_factory = sqlite3.Row
rows = db.execute("""
    SELECT a.name, al.provider, al.model, al.baseUrl
    FROM Agent a JOIN AgentLlmConfig al ON al.agentId = a.id
    WHERE a.name IN ('TrendSpy', 'Taskmaster', 'NoteGrab', 'Sentinel Watch')
""").fetchall()
for r in rows:
    print(f"{r['name']}: provider={r['provider']} model={r['model']} baseUrl={r['baseUrl']}")
db.close()
