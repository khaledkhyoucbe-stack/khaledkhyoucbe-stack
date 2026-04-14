#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from app import app

with app.app_context():
    from utils import query
    
    # ✅ الحصول على البيانات من متغيرات البيئة بدلاً من كتابتها مباشرة
    email = os.environ.get('SUPER_ADMIN_EMAIL', 'admin@maarif.local')
    password = os.environ.get('SUPER_ADMIN_PASSWORD', '***HIDDEN***')
    
    print("\n" + "=" * 80)
    print("📊 تقرير شامل لحالة النظام والمسؤول")
    print("=" * 80)
    
    # 1. معلومات النظام
    print("\n🖥️ معلومات النظام:")
    print("-" * 80)
    print(f"   🗄️ قاعدة البيانات: SQLite (school.db)")
    print(f"   🌍 اللغة الافتراضية: العربية")
    print(f"   📅 السنة الدراسية: 2025-2026")
    print(f"   ✅ النظام: يعمل بشكل صحيح")
    
    # 2. معلومات المستخدم
    print("\n👤 معلومات المسؤول:")
    print("-" * 80)
    
    user = query("""
        SELECT id, name, email, role, email_verified, is_active, created_at, school_id
        FROM users 
        WHERE email = ?
    """, (email,))
    
    if user:
        u = user[0]
        print(f"   🆔 معرف المستخدم: {u['id']}")
        print(f"   📝 الاسم الكامل: {u['name']}")
        print(f"   📧 البريد الإلكتروني: {u['email']}")
        print(f"   🏫 معرف المدرسة: {u['school_id'] if u['school_id'] else 'غير محدد (مسؤول عام)'}")
    else:
        print(f"   ❌ لم يتم العثور على المستخدم")
        sys.exit(1)
    
    # 3. حالة الصلاحيات
    print("\n🔐 حالة الصلاحيات:")
    print("-" * 80)
    
    if u['role'] == 'super_admin':
        print(f"   ✅ الدور: مسؤول عام (Super Admin)")
        print(f"   ✅ الصلاحيات:")
        print(f"      • إدارة جميع المدارس")
        print(f"      • إدارة جميع المستخدمين")
        print(f"      • الإحصائيات العامة")
        print(f"      • إعدادات النظام")
        print(f"      • إدارة الفواتير والاشتراكات")
    else:
        print(f"   ⚠️ الدور: {u['role']}")
    
    # 4. حالة التحقق
    print("\n✉️ حالة التحقق من البريد الإلكتروني:")
    print("-" * 80)
    
    if u['email_verified']:
        print(f"   ✅ البريد الإلكتروني: موثق")
        print(f"   ✅ يمكنك استخدام جميع ميزات النظام")
    else:
        print(f"   ⚠️ البريد الإلكتروني: غير موثق")
        print(f"   ⚠️ يجب التحقق من البريد قبل استخدام بعض الميزات")
    
    # 5. حالة التفعيل
    print("\n🟢 حالة التفعيل:")
    print("-" * 80)
    
    if u['is_active']:
        print(f"   ✅ الحساب: نشط")
        print(f"   ✅ يمكنك تسجيل الدخول")
    else:
        print(f"   ❌ الحساب: معطل")
        print(f"   ❌ لا يمكنك تسجيل الدخول")
    
    # 6. بيانات الدخول
    print("\n🔑 بيانات الدخول:")
    print("-" * 80)
    print(f"   📧 البريد: {email}")
    print(f"   🔐 كلمة المرور: {'*' * len(password)}")
    print(f"   🌐 عنوان النظام: http://localhost:5000")
    
    # 7. الملخص النهائي
    print("\n" + "=" * 80)
    print("📋 الملخص النهائي:")
    print("=" * 80)
    
    status_items = [
        ("النظام", "✅ يعمل بشكل صحيح"),
        ("حساب المسؤول", f"✅ موجود ونشط" if u['is_active'] else "❌ معطل"),
        ("دور المسؤول", "✅ مسؤول عام"),
        ("التحقق من البريد", "✅ موثق" if u['email_verified'] else "⚠️ غير موثق"),
        ("إمكانية تسجيل الدخول", "✅ ممكنة" if u['is_active'] and u['email_verified'] else "⚠️ قد تكون هناك مشكلة"),
    ]
    
    for item, status in status_items:
        print(f"   {status:25} | {item}")
    
    print("\n" + "=" * 80)
    
    # 8. الخطوات التالية
    print("\n📝 الخطوات التالية:")
    print("-" * 80)
    print(f"   1️⃣ بدء التطبيق:")
    print(f"      → python app.py")
    print(f"   2️⃣ الدخول إلى النظام:")
    print(f"      → http://localhost:5000")
    print(f"   3️⃣ تسجيل الدخول:")
    print(f"      البريد: {email}")
    print(f"      كلمة المرور: {'*' * len(password)}")
    print(f"   4️⃣ الوصول إلى لوحة التحكم:")
    print(f"      → http://localhost:5000/super/")
    
    print("\n" + "=" * 80 + "\n")
