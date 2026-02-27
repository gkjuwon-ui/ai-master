import sqlite3

db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = db.cursor()

# Chat rooms detail
print("=== CHAT ROOMS ===")
c.execute('''
    SELECT r.id, r.name, r.type, r.lastMessagePreview, r.lastMessageAt, r.createdAt
    FROM AgentChatRoom r
    ORDER BY r.createdAt DESC
''')
for row in c.fetchall():
    print(f"  Room: {row[0][:8]}... type={row[2]} name={row[1]} lastMsg={row[3]}")
    print(f"    lastMsgAt={row[4]} createdAt={row[5]}")

# Chat members
print("\n=== CHAT MEMBERS ===")
c.execute('''
    SELECT m.chatRoomId, m.profileId, p.displayName, m.role
    FROM AgentChatMember m
    JOIN AgentProfile p ON m.profileId = p.id
    ORDER BY m.chatRoomId
''')
for row in c.fetchall():
    print(f"  Room {row[0][:8]}... member={row[2]} role={row[3]}")

# Chat messages detail
print("\n=== CHAT MESSAGES ===")
c.execute('''
    SELECT msg.id, msg.chatRoomId, msg.senderId, p.displayName, msg.content, msg.messageType, msg.createdAt
    FROM AgentMessage msg
    JOIN AgentProfile p ON msg.senderId = p.id
    ORDER BY msg.createdAt ASC
''')
for row in c.fetchall():
    print(f"  [{row[6]}] Room {row[1][:8]}... {row[3]}: {row[4][:80]} (type={row[5]})")

# Notifications related to chat
print("\n=== CHAT NOTIFICATIONS ===")
c.execute('''
    SELECT n.id, n.profileId, p.displayName, n.type, n.title, n.createdAt
    FROM AgentNotification n
    JOIN AgentProfile p ON n.profileId = p.id
    WHERE n.type LIKE '%CHAT%' OR n.type LIKE '%MESSAGE%' OR n.type LIKE '%DM%'
    ORDER BY n.createdAt DESC
    LIMIT 20
''')
rows = c.fetchall()
if rows:
    for row in rows:
        print(f"  [{row[5]}] {row[2]}: type={row[3]} title={row[4]}")
else:
    print("  (no chat notifications found)")

# Check all notification types
print("\n=== ALL NOTIFICATION TYPES ===")
c.execute('SELECT type, COUNT(*) FROM AgentNotification GROUP BY type')
for row in c.fetchall():
    print(f"  {row[0]}: {row[1]}")

db.close()
