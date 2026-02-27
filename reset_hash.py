import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
cur = db.cursor()
cur.execute("UPDATE AgentProfile SET selfPromptHash = '' WHERE selfPromptHash IS NOT NULL AND selfPromptHash != ''")
print(f'Reset selfPromptHash for {cur.rowcount} agents')
db.commit()
db.close()
