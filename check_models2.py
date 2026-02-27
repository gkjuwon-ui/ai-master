import sqlite3, json

conn = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = conn.cursor()

# Agent has llmConfigId → LLMConfig table
c.execute("PRAGMA table_info(LLMConfig)")
for col in c.fetchall():
    print(f"  LLMConfig: {col[1]} ({col[2]})")

print()
c.execute("""
    SELECT a.name, l.provider, l.model 
    FROM Agent a 
    LEFT JOIN LLMConfig l ON a.llmConfigId = l.id
    ORDER BY a.name
""")
for row in c.fetchall():
    print(f"  {row[0]}: provider={row[1]}, model={row[2]}")

# Also count follow status
print("\n=== Follow Stats ===")
c.execute("SELECT status, COUNT(*) FROM AgentFollow GROUP BY status")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

c.execute("SELECT isMutual, COUNT(*) FROM AgentFollow GROUP BY isMutual")
for row in c.fetchall():
    print(f"  isMutual={row[0]}: {row[1]}")

print("\n=== Friends (mutual) ===")
c.execute("""
    SELECT f.followerId, fp.displayName, f.targetId, tp.displayName, f.status
    FROM AgentFollow f
    JOIN AgentProfile fp ON fp.id = f.followerId
    JOIN AgentProfile tp ON tp.id = f.targetId
""")
for row in c.fetchall():
    print(f"  {row[1]} → {row[3]}: status={row[4]}")

print("\n=== Chat Rooms ===")
c.execute("SELECT type, COUNT(*) FROM AgentChatRoom GROUP BY type")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

conn.close()
