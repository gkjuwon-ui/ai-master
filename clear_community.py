import sqlite3

db = r"C:\Users\gkjuw\AppData\Roaming\ogenti\data\ogenti.db"
conn = sqlite3.connect(db)
c = conn.cursor()

tables = ['PostView', 'CommunityVote', 'CommunityComment', 'CommunityPost']
for t in tables:
    try:
        c.execute(f'DELETE FROM "{t}"')
        print(f'Cleared {t}: {c.rowcount} rows deleted')
    except Exception as e:
        print(f'Skip {t}: {e}')

conn.commit()
conn.close()
print('All community data cleared.')
