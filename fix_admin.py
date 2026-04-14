#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from app import app

with app.app_context():
    from utils import execute, query
    
    print("\n" + "=" * 70)
    print("🔧 تحديث قاعدة البيانات")
    print("=" * 70)
    
    # ✅ الحصول على البيانات من متغيرات البيئة بدلاً من كتابتها مباشرة
    email = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@maarif.local')
    password = os.environ.get('SUPER_ADMIN_PASSWORD')
    
    if not email or not password:
        print("❌ خطأ: SUPER_ADMIN_EMAIL أو SUPER_ADMIN_PASSWORD غير محددة في .env")
        sys.exit(1)
    
    try:
        # 1. إضافة الأعمدة المفقودة
        print("\n1️⃣ إضافة الأعمدة المفقودة...")
        
        # إضافة العمود is_active
        try:
            execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            print("   ✅ تم إضافة عمود is_active")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("   ℹ️ العمود is_active موجود مسبقاً")
            else:
                raise
        
        # إضافة عمود email_verified
        try:
            execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
            print("   ✅ تم إضافة عمود email_verified")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("   ℹ️ العمود email_verified موجود مسبقاً")
            else:
                raise
        
        # إضافة عمود verification_token
        try:
            execute("ALTER TABLE users ADD COLUMN verification_token TEXT")
            print("   ✅ تم إضافة عمود verification_token")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("   ℹ️ العمود verification_token موجود مسبقاً")
            else:
                raise
        
        # إضافة عمود token_expires_at
        try:
            execute("ALTER TABLE users ADD COLUMN token_expires_at TEXT")
            print("   ✅ تم إضافة عمود token_expires_at")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("   ℹ️ العمود token_expires_at موجود مسبقاً")
            else:
                raise
        
        # 2. إنشاء أو تحديث المستخدم
        print("\n2️⃣ تحديث بيانات المسؤول...")
        
        from werkzeug.security import generate_password_hash
        import secrets
        from datetime import datetime, timedelta
        
        # تحقق من وجود المستخدم
        existing_user = query("SELECT id FROM users WHERE email = ?", (email,))
        
        if existing_user:
            print(f"   ℹ️ المستخدم موجود بالفعل (ID: {existing_user[0]['id']})")
            print(f"   📝 تحديث البيانات...")
            
            # تحديث المستخدم الموجود
            hashed_pwd = generate_password_hash(password)
            execute("""
                UPDATE users 
                SET name = ?, password = ?, role = ?, 
                    email_verified = 1, is_active = 1
                WHERE email = ?
            """, ('مسؤول النظام', hashed_pwd, 'super_admin', email))
            
        else:
            print(f"   ✨ إنشاء مستخدم جديد...")
            
            from werkzeug.security import generate_password_hash
            
            hashed_pwd = generate_password_hash(password)
            
            execute("""
                INSERT INTO users 
                (school_id, name, email, password, role, created_at, 
                 email_verified, is_active)
                VALUES (1, ?, ?, ?, ?, datetime('now'), 1, 1)
            """, ('مسؤول النظام', email, hashed_pwd, 'super_admin'))
        
        print(f"   ✅ تم:")
        print(f"      📧 البريد: {email}")
        print(f"      🔐 كلمة المرور: {'*' * len(password)}")
        print(f"      👤 الدور: super_admin (مسؤول عام)")
        print(f"      ✉️ البريد الإلكتروني: موثق ✅")
        print(f"      🟢 الحالة: نشط ✅")
        
        # 3. التحقق من إنشاء المستخدم
        print("\n3️⃣ التحقق النهائي...")
        
        user = query("""
            SELECT id, name, email, role, email_verified, is_active 
            FROM users 
            WHERE email = ?
        """, (email,))
        
        if user:
            u = user[0]
            print(f"\n✅ حالة المستخدم:\n")
            print(f"   🆔 المعرف: {u['id']}")
            print(f"   📝 الاسم: {u['name']}")
            print(f"   📧 البريد: {u['email']}")
            print(f"   👤 الدور: {u['role']}")
            print(f"   ✉️ التحقق من البريد: {'✅ موثق' if u['email_verified'] else '❌ غير موثق'}")
            print(f"   🟢 الحالة: {'✅ نشط' if u['is_active'] else '❌ معطل'}")
        else:
            print(f"   ❌ فشل في إنشاء المستخدم")
        
        print("\n" + "=" * 70)
        print("✅ تم تحديث قاعدة البيانات بنجاح!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}")
        import traceback
        traceback.print_exc()
