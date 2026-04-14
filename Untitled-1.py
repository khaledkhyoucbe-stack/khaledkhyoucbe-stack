# قبل (❌ سيؤ):
schools = query("SELECT * FROM schools")
for school in schools:
    count = query("SELECT COUNT(*) FROM students WHERE school_id=?", (school['id'],))
    # عدد queries: N + 1

# بعد (✅ محسّن):
schools_with_counts = query("""
    SELECT s.*,
           COUNT(st.id) as student_count
    FROM schools s
    LEFT JOIN students st ON st.school_id = s.id
    GROUP BY s.id
""")
# عدد queries: 1 فقط!

# في super_admin.py:
# الحالي:
schools = query("SELECT * FROM schools")
for school in schools:
    count = query("SELECT COUNT(*) FROM students WHERE school_id=?", (school['id'],))

# المحسّن:
schools = query("""
    SELECT s.*,
           (SELECT COUNT(*) FROM students WHERE school_id=s.id AND is_active=1) as student_count,
           (SELECT COUNT(*) FROM users WHERE school_id=s.id) as user_count,
           (SELECT COUNT(*) FROM classes WHERE school_id=s.id) as class_count
    FROM schools s
    ORDER BY s.created_at DESC
""")