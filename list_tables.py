import sqlite3

conn = sqlite3.connect('school.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

if tables:
    print("\n📊 الجداول الموجودة:\n")
    for table in tables:
        print(f"  ✓ {table[0]}")
else:
    print("\n❌ لا توجد جداول في قاعدة البيانات")
    print("قد تحتاج إلى تشغيل الترحيلات (migrations) أولاً")

conn.close()
