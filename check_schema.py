import sqlite3

conn = sqlite3.connect('test_maarif.db')
c = conn.cursor()
c.execute("PRAGMA table_info(users)")
cols = c.fetchall()
for col in cols:
    print(f"{col[1]}: {col[2]}")
conn.close()
