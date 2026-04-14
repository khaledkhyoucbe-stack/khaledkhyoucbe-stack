#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import json
from pathlib import Path

db_path = "maarif.db"

if not Path(db_path).exists():
    print(f"❌ ملف قاعدة البيانات غير موجود: {db_path}")
    exit(1)

print("\n" + "=" * 80)
print("📖 قراءة ملف قاعدة البيانات: maarif.db")
print("=" * 80)

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. الحصول على قائمة الجداول
    print("\n📊 الجداول الموجودة في قاعدة البيانات:")
    print("-" * 80)
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    
    if tables:
        for i, table in enumerate(tables, 1):
            table_name = table['name']
            
            # الحصول على عدد الصفوف
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cursor.fetchone()['count']
            
            print(f"   {i:2}. {table_name:25} → {count:6} صف")
    else:
        print("   ❌ لا توجد جداول")
    
    # 2. معلومات المدارس
    print("\n" + "-" * 80)
    print("🏫 معلومات المدارس:")
    print("-" * 80)
    
    cursor.execute("SELECT id, name, slug, plan, is_active, created_at FROM schools ORDER BY id")
    schools = cursor.fetchall()
    
    for school in schools:
        status = "✅ نشطة" if school['is_active'] else "❌ غير نشطة"
        print(f"   ID: {school['id']}")
        print(f"      • الاسم: {school['name']}")
        print(f"      • الوصف: {school['slug']}")
        print(f"      • الخطة: {school['plan']}")
        print(f"      • الحالة: {status}")
        print(f"      • التاريخ: {school['created_at']}")
        print()
    
    # 3. معلومات المستخدمين
    print("-" * 80)
    print("👥 معلومات المستخدمين:")
    print("-" * 80)
    
    cursor.execute("""
        SELECT id, name, email, role, school_id, created_at 
        FROM users 
        ORDER BY role, id
    """)
    users = cursor.fetchall()
    
    roles_count = {}
    for user in users:
        role = user['role']
        roles_count[role] = roles_count.get(role, 0) + 1
    
    print(f"   إجمالي المستخدمين: {len(users)}")
    print(f"   توزيع الأدوار:")
    for role, count in sorted(roles_count.items()):
        print(f"      • {role}: {count}")
    
    print(f"\n   قائمة المستخدمين:")
    for user in users:
        print(f"      ID: {user['id']:4} | {user['name']:20} | {user['email']:30} | {user['role']:15}")
    
    # 4. معلومات الفصول
    print("\n" + "-" * 80)
    print("📚 معلومات الفصول:")
    print("-" * 80)
    
    cursor.execute("SELECT id, name, level, school_year, school_id FROM classes ORDER BY school_id, id")
    classes = cursor.fetchall()
    
    print(f"   إجمالي الفصول: {len(classes)}")
    for cls in classes:
        print(f"      • {cls['name']:20} | {cls['level']:10} | {cls['school_year']:15} | School: {cls['school_id']}")
    
    # 5. معلومات الطلاب
    print("\n" + "-" * 80)
    print("🎓 معلومات الطلاب:")
    print("-" * 80)
    
    cursor.execute("""
        SELECT id, name, gender, birth_date, class_id, school_id 
        FROM students 
        LIMIT 20
    """)
    students = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) as count FROM students")
    total_students = cursor.fetchone()['count']
    
    print(f"   إجمالي الطلاب: {total_students}")
    print(f"   عرض أول 20 طالب:")
    
    for student in students:
        print(f"      • {student['name']:30} | {student['gender']:5} | {student['birth_date']:10} | Class: {student['class_id']}")
    
    # 6. معلومات الدرجات
    print("\n" + "-" * 80)
    print("📊 معلومات الدرجات:")
    print("-" * 80)
    
    cursor.execute("SELECT COUNT(*) as count FROM grades")
    grades_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT exam_type, COUNT(*) as count FROM grades GROUP BY exam_type")
    grade_types = cursor.fetchall()
    
    print(f"   إجمالي الدرجات: {grades_count}")
    print(f"   أنواع الاختبارات:")
    for gtype in grade_types:
        print(f"      • {gtype['exam_type']}: {gtype['count']}")
    
    # 7. معلومات الحضور
    print("\n" + "-" * 80)
    print("✅ معلومات الحضور:")
    print("-" * 80)
    
    cursor.execute("SELECT COUNT(*) as count FROM attendance")
    attendance_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT DISTINCT month FROM attendance ORDER BY month")
    months = cursor.fetchall()
    
    print(f"   إجمالي سجلات الحضور: {attendance_count}")
    print(f"   الأشهر: {', '.join([m['month'] for m in months])}")
    
    # 8. معلومات الرسوم والدفعات
    print("\n" + "-" * 80)
    print("💰 معلومات الرسوم والدفعات:")
    print("-" * 80)
    
    cursor.execute("SELECT COUNT(*) as count FROM fees")
    fees_count = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM payments")
    payments_count = cursor.fetchone()['count']
    
    print(f"   إجمالي الرسوم المعرفة: {fees_count}")
    print(f"   إجمالي الدفعات: {payments_count}")
    
    # 9. معلومات الملخص
    print("\n" + "=" * 80)
    print("📋 ملخص قاعدة البيانات:")
    print("=" * 80)
    
    summary = {
        "المدارس": len(schools),
        "المستخدمين": len(users),
        "الفصول": len(classes),
        "الطلاب": total_students,
        "الدرجات": grades_count,
        "سجلات الحضور": attendance_count,
        "الرسوم": fees_count,
        "الدفعات": payments_count,
    }
    
    for key, value in summary.items():
        print(f"   📍 {key:20}: {value:6}")
    
    print("\n" + "=" * 80 + "\n")
    
    conn.close()

except sqlite3.Error as e:
    print(f"❌ خطأ في قراءة قاعدة البيانات: {e}")
except Exception as e:
    print(f"❌ خطأ: {e}")
    import traceback
    traceback.print_exc()
