import sqlite3, json

conn = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = conn.cursor()

# Check LLMConfig entries
print("=== LLMConfig table ===")
c.execute("SELECT id, name, provider, model, isDefault FROM LLMConfig")
for r in c.fetchall():
    print(f"  id={r[0][:10]}.. name={r[1]} prov={r[2]} model={r[3]} default={r[4]}")

# Check agents' llmConfigId
print("\n=== Agent llmConfigId (non-null) ===")
c.execute("SELECT name, llmConfigId FROM Agent WHERE llmConfigId IS NOT NULL LIMIT 10")
rows = c.fetchall()
print(f"  Count: {len(rows)}")
for r in rows:
    print(f"  {r[0]}: configId={r[1][:10] if r[1] else 'NULL'}..")

print("\n=== Agent llmConfigId NULL count ===")
c.execute("SELECT COUNT(*) FROM Agent WHERE llmConfigId IS NULL")
print(f"  NULL: {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM Agent WHERE llmConfigId IS NOT NULL")
print(f"  Set: {c.fetchone()[0]}")

# Check how runtime gets the agent config
# Look at the idle_engagement registration to understand how agents get their model
print("\n=== Pending follow analysis ===")
c.execute("""
    SELECT tp.displayName, COUNT(*) as cnt
    FROM AgentFollow f 
    JOIN AgentProfile tp ON tp.id = f.targetId
    WHERE f.status = 'PENDING'
    GROUP BY f.targetId
    ORDER BY cnt DESC
    LIMIT 10
""")
for r in c.fetchall():
    print(f"  {r[0]}: {r[1]} pending incoming follows")

conn.close()
