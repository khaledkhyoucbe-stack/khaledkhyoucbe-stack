#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from app import app

with app.app_context():
    from utils import execute, query
    
    print("\n" + "=" * 70)
    print("🔧 تثبيت وتهيئة قاعدة البيانات")
    print("=" * 70)
    
    # 1. إنشاء الجداول الأساسية
    print("\n1️⃣ إنشاء جداول قاعدة البيانات...")
    
    try:
        # إنشاء جدول schools
        execute("""
            CREATE TABLE IF NOT EXISTS schools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT UNIQUE NOT NULL,
                plan TEXT DEFAULT 'basic',
                is_active INTEGER DEFAULT 1,
                max_students INTEGER DEFAULT 500,
                contact_email TEXT,
                contact_phone TEXT,
                address TEXT,
                created_at TEXT,
                sync_id TEXT UNIQUE,
                sync_status TEXT DEFAULT 'pending',
                last_modified TEXT,
                is_deleted INTEGER DEFAULT 0
            )
        """)
        print("   ✅ جدول schools تم إنشاؤه")
        
        # إنشاء جدول users
        execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'teacher',
                subject_code TEXT,
                phone TEXT,
                created_at TEXT,
                sync_id TEXT UNIQUE,
                sync_status TEXT DEFAULT 'pending',
                last_modified TEXT,
                is_deleted INTEGER DEFAULT 0,
                email_verified INTEGER DEFAULT 0,
                verification_token TEXT,
                token_expires_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)
        print("   ✅ جدول users تم إنشاؤه")
        
        # 2. إنشاء مدرسة افتراضية
        print("\n2️⃣ إنشاء مدرسة افتراضية...")
        
        execute("""
            INSERT OR IGNORE INTO schools (name, slug, is_active, created_at)
            VALUES (?, ?, 1, datetime('now'))
        """, ('مدرسة التجربة', 'test-school'))
        
        school = query("SELECT id FROM schools LIMIT 1")
        if school:
            school_id = school[0]['id']
            print(f"   ✅ مدرسة تم إنشاؤها برقم: {school_id}")
        else:
            school_id = None
            print(f"   ❌ فشل في إنشاء المدرسة")
        
        # 3. إنشاء المستخدم الجديد
        print("\n3️⃣ إنشاء حساب مسؤول...")
        
        from werkzeug.security import generate_password_hash
        import secrets
        from datetime import datetime, timedelta
        
        email = "ballak727@gmail.com"
        password = "43754590"
        hashed_pwd = generate_password_hash(password)
        
        # إنشاء رمز التحقق
        verification_token = secrets.token_urlsafe(32)
        token_expires = (datetime.now() + timedelta(days=1)).isoformat()
        
        execute("""
            INSERT OR REPLACE INTO users 
            (school_id, name, email, password, role, created_at, 
             email_verified, verification_token, token_expires_at, is_active)
            VALUES (?, ?, ?, ?, ?, datetime('now'), 1, ?, ?, 1)
        """, (school_id, 'مسؤول النظام', email, hashed_pwd, 'super_admin', 
              verification_token, token_expires))
        
        print(f"   ✅ تم إنشاء المستخدم:")
        print(f"      📧 البريد: {email}")
        print(f"      🔐 كلمة المرور: {'*' * len(password)}")
        print(f"      👤 الدور: super_admin")
        print(f"      ✉️ البريد الإلكتروني: موثق ✅")
        
        # 4. التحقق من إنشاء المستخدم
        print("\n4️⃣ التحقق من المستخدم...")
        
        user = query("""
            SELECT id, name, email, role, email_verified, is_active 
            FROM users 
            WHERE email = ?
        """, (email,))
        
        if user:
            u = user[0]
            print(f"   ✅ تم العثور على المستخدم:")
            print(f"      🆔 المعرف: {u['id']}")
            print(f"      📝 الاسم: {u['name']}")
            print(f"      👤 الدور: {u['role']}")
            print(f"      ✉️ التحقق: {'✅ موثق' if u['email_verified'] else '❌ غير موثق'}")
        else:
            print(f"   ❌ فشل في إنشاء المستخدم")
        
        print("\n" + "=" * 70)
        print("✅ تم تهيئة قاعدة البيانات بنجاح!")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ خطأ: {str(e)}")
        import traceback
        traceback.print_exc()
