import sqlite3
db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = db.cursor()
c.execute("""SELECT p.displayName, p.ownerId, m.chatRoomId 
FROM AgentChatMember m 
JOIN AgentProfile p ON m.profileId = p.id 
ORDER BY m.chatRoomId""")
for r in c.fetchall():
    print(f"  {r[0]}: owner={r[1]} room={r[2][:8]}...")
# Count how many rooms the owner sees
c.execute("""SELECT COUNT(*) FROM AgentChatMember m 
JOIN AgentProfile p ON m.profileId = p.id""")
print(f"\nTotal memberships (= items in owner-rooms): {c.fetchone()[0]}")
c.execute("SELECT COUNT(*) FROM AgentChatRoom")
print(f"Actual unique rooms: {c.fetchone()[0]}")
db.close()
