import sqlite3
import os

db_path = 'data/emby_pulse.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, title, content, is_active FROM announcements")
    rows = c.fetchall()
    print(f'公告数量: {len(rows)}')
    for row in rows:
        print(f'ID={row[0]}, title={row[1]}, content={row[2][:50] if row[2] else "NULL"}..., is_active={row[3]}')
    conn.close()
else:
    print(f'数据库不存在: {db_path}')