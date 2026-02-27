import sqlite3

db = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db)
c = conn.cursor()

# Reset all selfPromptHash to force regeneration on next load
c.execute('UPDATE "AgentProfile" SET "selfPromptHash" = \'force-refresh\'')
print(f'Reset selfPromptHash for {c.rowcount} profiles')

conn.commit()
conn.close()
print('Done - all agents will get new self-prompts on next startup')
