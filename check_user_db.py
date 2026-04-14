#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sqlite3
import hashlib
import sys
from datetime import datetime

def check_user_database():
    """التحقق من حالة المستخدم في قاعدة البيانات"""
    
    try:
        # الاتصال بقاعدة البيانات
        conn = sqlite3.connect('school.db')
        cursor = conn.cursor()
        
        email = "ballak727@gmail.com"
        
        print("\n" + "=" * 70)
        print("🗄️ فحص قاعدة البيانات")
        print("=" * 70)
        
        # البحث عن المستخدم
        cursor.execute("""
            SELECT id, name, email, role, email_verified, 
                   created_at, is_active, school_id
            FROM users 
            WHERE email = ?
        """, (email,))
        
        result = cursor.fetchone()
        
        if result:
            user_id, name, email_db, role, email_verified, created_at, is_active, school_id = result
            
            print(f"\n✅ تم العثور على المستخدم:")
            print("-" * 70)
            print(f"🆔 معرف المستخدم: {user_id}")
            print(f"📝 الاسم: {name}")
            print(f"📧 البريد: {email_db}")
            print(f"👤 الدور: {role}")
            print(f"✉️ التحقق من البريد: {'✅ موثق' if email_verified == 1 else '❌ غير موثق'}")
            print(f"🟢 الحالة: {'✅ نشط' if is_active == 1 else '❌ معطل'}")
            print(f"📅 تاريخ الإنشاء: {created_at}")
            print(f"🏫 معرف المدرسة: {school_id}")
            
            # التحقق من الصلاحيات
            print("\n" + "-" * 70)
            print("🔐 الصلاحيات المتاحة:")
            print("-" * 70)
            
            if role == "super_admin":
                print("✅ مسؤول عام (Super Admin) - صلاحيات كاملة")
                print("   • إدارة المدارس")
                print("   • إدارة المستخدمين")
                print("   • الإحصائيات العامة")
                print("   • الإعدادات العامة")
            elif role == "admin":
                print("✅ مسؤول المدرسة (Admin)")
                print("   • إدارة الطلاب")
                print("   • إدارة المعلمين")
                print("   • إدارة الدرجات")
                print("   • التقارير")
            elif role == "teacher":
                print("✅ معلم (Teacher)")
                print("   • إدارة الفصل")
                print("   • تحديد الدرجات")
                print("   • تحديد الحضور")
            else:
                print(f"⚠️ دور غير معروف: {role}")
            
            # التحقق من توثيق البريد
            print("\n" + "-" * 70)
            print("📧 حالة توثيق البريد الإلكتروني:")
            print("-" * 70)
            
            if email_verified == 1:
                print("✅ البريد الإلكتروني موثق")
                print("   يمكنك استخدام جميع ميزات النظام")
            else:
                print("❌ البريد الإلكتروني غير موثق")
                print("   يجب التحقق من البريد قبل استخدام بعض الميزات")
                
                # البحث عن رمز التحقق
                cursor.execute("""
                    SELECT verification_token, token_expires_at 
                    FROM users 
                    WHERE email = ? AND verification_token IS NOT NULL
                """, (email,))
                
                token_result = cursor.fetchone()
                if token_result:
                    token, expires_at = token_result
                    print(f"\n   📝 رمز التحقق: {token[:10]}...")
                    print(f"   ⏰ صلاحية الرمز: {expires_at}")
                    
                    # التحقق من انتهاء صلاحية الرمز
                    expiry_time = datetime.fromisoformat(expires_at)
                    now = datetime.now()
                    if now > expiry_time:
                        print(f"   ⚠️ انتهت صلاحية رمز التحقق")
                    else:
                        print(f"   ✅ رمز التحقق صالح")
            
            # النتائج النهائية
            print("\n" + "=" * 70)
            print("✅ ملخص حالة النظام:")
            print("=" * 70)
            print(f"حالة المسؤول: {'✅ فعال' if is_active == 1 else '❌ معطل'}")
            print(f"دور المسؤول: {role}")
            print(f"توثيق البريد: {'✅ موثق' if email_verified == 1 else '❌ غير موثق'}")
            print(f"حالة النظام: {'✅ جاهز' if is_active and email_verified else '⚠️ يحتاج تفعيل'}")
            print("=" * 70 + "\n")
            
            conn.close()
            return True
        else:
            print(f"\n❌ لم يتم العثور على المستخدم: {email}")
            print("\n💡 تلميح: تأكد من أن البريد الإلكتروني صحيح")
            conn.close()
            return False
            
    except sqlite3.OperationalError as e:
        print(f"\n❌ خطأ قاعدة البيانات: {str(e)}")
        return False
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = check_user_database()
    sys.exit(0 if success else 1)
