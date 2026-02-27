import sqlite3

db = sqlite3.connect(r'C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db')
c = db.cursor()

# Check message tables
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%essage%'")
print('Message tables:', c.fetchall())

# Check AgentChatRoom
c.execute('SELECT COUNT(*) FROM AgentChatRoom')
print('Chat rooms:', c.fetchone()[0])

# Check AgentMessage
try:
    c.execute('SELECT COUNT(*) FROM AgentMessage')
    print('Agent messages:', c.fetchone()[0])
except Exception as e:
    print('AgentMessage error:', e)

# Follow status counts
c.execute('SELECT status, COUNT(*) FROM AgentFollow GROUP BY status')
print('Follow status counts:', c.fetchall())

# Mutual follows
c.execute('SELECT COUNT(*) FROM AgentFollow WHERE isMutual=1')
print('Mutual follows:', c.fetchone()[0])

# Show all accepted follows with names
c.execute('''
    SELECT 
        fp.displayName as follower, 
        tp.displayName as target, 
        f.status, 
        f.isMutual
    FROM AgentFollow f
    JOIN AgentProfile fp ON f.followerId = fp.id
    JOIN AgentProfile tp ON f.targetId = tp.id
    WHERE f.status = 'ACCEPTED'
    ORDER BY f.isMutual DESC, f.updatedAt DESC
''')
print('\nAccepted follows:')
for row in c.fetchall():
    print(f'  {row[0]} -> {row[1]} (mutual={row[3]})')

db.close()
