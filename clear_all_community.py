"""Clear all community data and reset selfPrompt hashes for regeneration."""
import sqlite3
import os

db_path = os.path.join(os.environ.get("APPDATA", ""), "ogenti", "data", "ogenti.db")
if not os.path.exists(db_path):
    print(f"DB not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Count before
tables = [
    ("ElectionVote", "Election votes"),
    ("ElectionCandidate", "Election candidates"),
    ("Election", "Elections"),
    ("GovernanceProposal", "Governance proposals"),
    ("CommunityPost", "Community posts"),
    ("CommunityComment", "Comments"),
    ("CommunityVote", "Votes"),
    ("PostView", "Post views"),
    ("AgentImpression", "Impressions"),
    ("AgentCreditTransfer", "Tips"),
    ("AgentMessage", "Messages"),
    ("AgentChatMember", "Chat members"),
    ("AgentChatRoom", "Chat rooms"),
    ("AgentNotification", "Notifications"),
    ("AgentFollow", "Follows"),
]

print("=== BEFORE CLEARING ===")
for table, label in tables:
    try:
        c.execute(f"SELECT COUNT(*) FROM {table}")
        count = c.fetchone()[0]
        print(f"  {label}: {count}")
    except:
        print(f"  {label}: (table not found)")

# Delete in dependency order
print("\n=== CLEARING DATA ===")
for table, label in tables:
    try:
        c.execute(f"DELETE FROM {table}")
        print(f"  Cleared {label}: {c.rowcount} rows deleted")
    except Exception as e:
        print(f"  {label}: error - {e}")

# Reset selfPrompt hashes to force regeneration
c.execute("UPDATE AgentProfile SET selfPromptHash = 'force-refresh'")
print(f"\n  Reset {c.rowcount} AgentProfile selfPromptHash to 'force-refresh'")

# Reset social counts
c.execute("UPDATE AgentProfile SET followerCount = 0, followingCount = 0, friendCount = 0, postCount = 0")
print(f"  Reset social counts for {c.rowcount} profiles")

conn.commit()

# Verify
print("\n=== AFTER CLEARING ===")
for table, label in tables:
    try:
        c.execute(f"SELECT COUNT(*) FROM {table}")
        count = c.fetchone()[0]
        print(f"  {label}: {count}")
    except:
        pass

c.execute("SELECT COUNT(*) FROM AgentProfile WHERE selfPromptHash = 'force-refresh'")
print(f"  Profiles pending prompt refresh: {c.fetchone()[0]}")

conn.close()
print("\n✓ Community fully reset. Restart OGENTI to regenerate selfPrompts.")
