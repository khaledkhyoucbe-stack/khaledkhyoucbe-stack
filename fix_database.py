#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
🔧 سكريبت إصلاح قاعدة البيانات
المهمة: إضافة الأعمدة الناقصة وإنشاء جداول جديدة
التاريخ: 6 أبريل 2026
"""

import os
import sqlite3
import sys
from datetime import datetime

def get_db_path():
    """الحصول على مسار قاعدة البيانات"""
    db_file = os.environ.get('DB_PATH', 'school.db')
    return db_file

def connect_db():
    """الاتصال بقاعدة البيانات"""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        print(f"✅ تم الاتصال بـ: {db_path}")
        return conn
    except Exception as e:
        print(f"❌ خطأ في الاتصال: {e}")
        sys.exit(1)

def check_column_exists(conn, table, column):
    """التحقق من وجود عمود"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table});")
    columns = [row[1] for row in cursor.fetchall()]
    return column in columns

def add_column_if_missing(conn, table, column, column_type, default=None):
    """إضافة عمود إذا كان ناقصاً"""
    if check_column_exists(conn, table, column):
        print(f"  ⏭️  العمود '{column}' موجود بالفعل في {table}")
        return
    
    cursor = conn.cursor()
    try:
        if default is not None:
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {column_type} DEFAULT {default}"
        else:
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
        
        cursor.execute(sql)
        conn.commit()
        print(f"  ✅ تم إضافة العمود '{column}' إلى {table}")
    except Exception as e:
        print(f"  ❌ خطأ في إضافة '{column}': {e}")

def create_sync_tables(conn):
    """إنشاء جداول المزامنة الجديدة"""
    cursor = conn.cursor()
    
    # جدول sync_queue
    print("\n📋 إنشاء جداول المزامنة...")
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_queue (
                id TEXT PRIMARY KEY,
                school_id TEXT NOT NULL,
                device_id TEXT,
                operation_type TEXT NOT NULL,
                table_name TEXT,
                record_id TEXT,
                data_json TEXT,
                local_status TEXT DEFAULT 'pending',
                server_version INTEGER DEFAULT 0,
                sync_attempts INTEGER DEFAULT 0,
                last_error TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(school_id) REFERENCES schools(id)
            )
        """)
        print("  ✅ تم إنشاء جدول sync_queue")
    except Exception as e:
        print(f"  ⏭️  جدول sync_queue موجود: {e}")
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_conflicts (
                id TEXT PRIMARY KEY,
                school_id TEXT NOT NULL,
                device_id TEXT,
                table_name TEXT,
                record_id TEXT,
                local_data TEXT,
                server_data TEXT,
                conflict_type TEXT,
                status TEXT DEFAULT 'pending',
                user_resolution TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT,
                FOREIGN KEY(school_id) REFERENCES schools(id)
            )
        """)
        print("  ✅ تم إنشاء جدول sync_conflicts")
    except Exception as e:
        print(f"  ⏭️  جدول sync_conflicts موجود: {e}")
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_imports (
                id TEXT PRIMARY KEY,
                school_id TEXT NOT NULL,
                device_id TEXT,
                import_type TEXT,
                file_name TEXT,
                sheet_name TEXT,
                parsed_data TEXT,
                validation_errors TEXT,
                status TEXT DEFAULT 'pending_preview',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(school_id) REFERENCES schools(id)
            )
        """)
        print("  ✅ تم إنشاء جدول pending_imports")
    except Exception as e:
        print(f"  ⏭️  جدول pending_imports موجود: {e}")
    
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                id TEXT PRIMARY KEY,
                school_id TEXT NOT NULL,
                device_id TEXT,
                last_sync_timestamp TEXT,
                last_sync_record_count INTEGER,
                offline_enabled INTEGER DEFAULT 0,
                FOREIGN KEY(school_id) REFERENCES schools(id)
            )
        """)
        print("  ✅ تم إنشاء جدول sync_metadata")
    except Exception as e:
        print(f"  ⏭️  جدول sync_metadata موجود: {e}")
    
    conn.commit()

def add_missing_columns(conn):
    """إضافة الأعمدة الناقصة إلى الجداول الموجودة"""
    print("\n🔧 إضافة الأعمدة الناقصة...\n")
    
    # جدول students
    print("📚 جدول students:")
    add_column_if_missing(conn, "students", "email", "TEXT")
    add_column_if_missing(conn, "students", "device_id", "TEXT")
    add_column_if_missing(conn, "students", "is_offline_created", "INTEGER", "0")
    add_column_if_missing(conn, "students", "offline_synced_at", "TEXT")
    
    # جدول payments
    print("\n💰 جدول payments:")
    add_column_if_missing(conn, "payments", "device_id", "TEXT")
    add_column_if_missing(conn, "payments", "sync_status", "TEXT", "'synced'")
    add_column_if_missing(conn, "payments", "is_offline_created", "INTEGER", "0")
    
    # جدول grades
    print("\n📊 جدول grades:")
    add_column_if_missing(conn, "grades", "device_id", "TEXT")
    add_column_if_missing(conn, "grades", "is_offline_created", "INTEGER", "0")
    
    # جدول attendance
    print("\n📋 جدول attendance:")
    add_column_if_missing(conn, "attendance", "device_id", "TEXT")
    add_column_if_missing(conn, "attendance", "is_offline_created", "INTEGER", "0")
    
    # جدول classes
    print("\n🏫 جدول classes:")
    add_column_if_missing(conn, "classes", "device_id", "TEXT")
    
    conn.commit()

def create_indexes(conn):
    """إنشاء فهارس لتحسين الأداء"""
    print("\n⚡ إنشاء الفهارس...\n")
    
    cursor = conn.cursor()
    
    # قائمة الفهارس
    indexes = [
        ("idx_sync_queue_pending", "sync_queue", "(school_id, local_status)"),
        ("idx_sync_queue_device", "sync_queue", "(device_id)"),
        ("idx_payments_school", "payments", "(school_id)"),
        ("idx_payments_student", "payments", "(student_id)"),
        ("idx_grades_student", "grades", "(student_id)"),
        ("idx_students_school", "students", "(school_id)"),
        ("idx_attendance_student", "attendance", "(student_id)"),
    ]
    
    for index_name, table_name, columns in indexes:
        try:
            sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}{columns}"
            cursor.execute(sql)
            print(f"  ✅ فهرس: {index_name}")
        except Exception as e:
            print(f"  ⏭️  فهرس {index_name} موجود أو خطأ: {str(e)[:50]}")
    
    conn.commit()

def get_database_stats(conn):
    """الحصول على إحصائيات قاعدة البيانات"""
    print("\n📊 إحصائيات قاعدة البيانات:\n")
    
    cursor = conn.cursor()
    
    # عدد الجداول
    cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
    tables_count = cursor.fetchone()[0]
    print(f"  📋 عدد الجداول: {tables_count}")
    
    # عدد السجلات في كل جدول
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]
    
    print(f"\n  سجلات كل جدول:")
    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"    {table}: {count} سجل")
        except:
            pass
    
    # حجم قاعدة البيانات
    db_path = get_db_path()
    if os.path.exists(db_path):
        size_mb = os.path.getsize(db_path) / (1024 * 1024)
        print(f"\n  💾 حجم الملف: {size_mb:.2f} MB")

def main():
    """الدالة الرئيسية"""
    print("=" * 60)
    print(" 🔧 سكريبت إصلاح قاعدة البيانات - مدرستي")
    print("=" * 60)
    
    # الاتصال بقاعدة البيانات
    conn = connect_db()
    
    try:
        # إضافة الأعمدة الناقصة
        add_missing_columns(conn)
        
        # إنشاء جداول المزامنة
        create_sync_tables(conn)
        
        # إنشاء الفهارس
        create_indexes(conn)
        
        # الإحصائيات
        get_database_stats(conn)
        
        print("\n" + "=" * 60)
        print("✅ تم إصلاح قاعدة البيانات بنجاح!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ خطأ عام: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
