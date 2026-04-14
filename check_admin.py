#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

# تعرّف على نوع قاعدة البيانات
use_pg = os.environ.get('DATABASE_URL', '').startswith('postgresql')

print("\n" + "=" * 70)
print("🔍 فحص حالة النظام")
print("=" * 70)

if use_pg:
    print("\n📊 نوع قاعدة البيانات: PostgreSQL")
    print(f"   🔗 اتصال: {os.environ.get('DATABASE_URL', 'غير محدد')[:50]}...")
    
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get('DATABASE_URL'))
        cursor = conn.cursor()
        
        # البحث عن المستخدم
        query = """
            SELECT id, name, email, role, email_verified, is_active 
            FROM users 
            WHERE email = %s
        """
        cursor.execute(query, ("ballak727@gmail.com",))
        result = cursor.fetchone()
        
        if result:
            user_id, name, email, role, email_verified, is_active = result
            print(f"\n✅ تم العثور على المستخدم:")
            print(f"   🆔 المعرف: {user_id}")
            print(f"   📝 الاسم: {name}")
            print(f"   📧 البريد: {email}")
            print(f"   👤 الدور: {role}")
            print(f"   ✉️ التحقق من البريد: {'✅ موثق' if email_verified else '❌ غير موثق'}")
            print(f"   🟢 الحالة: {'✅ نشط' if is_active else '❌ معطل'}")
        else:
            print(f"\n❌ لم يتم العثور على المستخدم: ballak727@gmail.com")
        
        cursor.close()
        conn.close()
        
    except ImportError:
        print("❌ مكتبة psycopg2 غير مثبتة")
    except Exception as e:
        print(f"❌ خطأ الاتصال: {str(e)}")

else:
    print("\n📊 نوع قاعدة البيانات: SQLite")
    
    try:
        import sqlite3
        conn = sqlite3.connect('school.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # تحقق من وجود الجدول
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not cursor.fetchone():
            print("❌ جدول users غير موجود")
            print("   🔧 قم بتشغيل: python init_db.py")
        else:
            # البحث عن المستخدم
            cursor.execute("""
                SELECT id, name, email, role, email_verified, is_active 
                FROM users 
                WHERE email = ?
            """, ("ballak727@gmail.com",))
            
            result = cursor.fetchone()
            
            if result:
                print(f"\n✅ تم العثور على المستخدم:")
                print(f"   🆔 المعرف: {result['id']}")
                print(f"   📝 الاسم: {result['name']}")
                print(f"   📧 البريد: {result['email']}")
                print(f"   👤 الدور: {result['role']}")
                print(f"   ✉️ التحقق من البريد: {'✅ موثق' if result['email_verified'] else '❌ غير موثق'}")
                print(f"   🟢 الحالة: {'✅ نشط' if result['is_active'] else '❌ معطل'}")
            else:
                print(f"\n❌ لم يتم العثور على المستخدم: ballak727@gmail.com")
                print("\n💡 المستخدمون الموجودون:")
                cursor.execute("SELECT id, name, email, role FROM users LIMIT 10")
                users = cursor.fetchall()
                if users:
                    for user in users:
                        print(f"   - {user['email']} ({user['role']})")
                else:
                    print("   لا توجد مستخدمون")
        
        conn.close()
        
    except sqlite3.OperationalError as e:
        print(f"❌ خطأ قاعدة البيانات: {e}")
    except Exception as e:
        print(f"❌ خطأ: {str(e)}")

print("\n" + "=" * 70 + "\n")
