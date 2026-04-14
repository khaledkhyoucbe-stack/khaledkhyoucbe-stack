#!/usr/bin/env python
# -*- coding: utf-8 -*-

from app import app, init_db

try:
    # تهيئة قاعدة البيانات
    with app.app_context():
        init_db()
        print("✅ تم تهيئة قاعدة البيانات بنجاح")
except Exception as e:
    print(f"❌ خطأ في تهيئة قاعدة البيانات: {str(e)}")
    import traceback
    traceback.print_exc()
