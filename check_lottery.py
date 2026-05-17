import sqlite3
import os

db_path = 'C:/Users/35956/Desktop/EmbyPulse-Pro/data/system.db'
print(f'DB exists: {os.path.exists(db_path)}')
conn = sqlite3.connect(db_path)
c = conn.cursor()

print('=== lottery_results table ===')
c.execute('SELECT * FROM lottery_results ORDER BY draw_date DESC LIMIT 5')
for r in c.fetchall():
    print(r)

print('\n=== lottery_tickets table ===')
c.execute('SELECT * FROM lottery_tickets ORDER BY id DESC LIMIT 10')
for t in c.fetchall():
    print(t)

print('\n=== lottery_winners table ===')
c.execute('SELECT * FROM lottery_winners ORDER BY id DESC LIMIT 5')
for w in c.fetchall():
    print(w)

conn.close()
