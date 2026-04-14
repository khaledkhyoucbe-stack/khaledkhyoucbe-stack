import os, re, time, json
from functools import wraps
from flask import request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

CURRENT_YEAR = os.environ.get('CURRENT_YEAR', '2025-2026')

# ── ثوابت ───────────────────────────────────────────────────────────
SUBJECTS = [
    ('MT','رياضيات'),('SN','علوم طبيعية'),('PC','فيزياء وكيمياء'),
    ('AR','عربية'),('FR','فرنسية'),('AN','إنجليزية'),
    ('IR','تربية إسلامية'),('PS','فلسفة'),
]
LEVELS = {
    'primary':   {'label':'ابتدائي', 'grades':['السنة 1','السنة 2','السنة 3','السنة 4','السنة 5','السنة 6']},
    'middle':    {'label':'إعدادي',  'grades':['السنة 1','السنة 2','السنة 3','السنة 4']},
    'secondary': {'label':'ثانوي',   'grades':['السنة 1','السنة 2','السنة 3']},
}
SECTIONS = ['أ', 'ب', 'ج', 'د']

# ── النظام الموريتاني للشعب الثانوية ─────────────────────────────────
MAURITANIAN_TRACKS = {
    'C': {'ar': 'شعبة الرياضيات',        'fr': 'Mathématiques'},
    'D': {'ar': 'شعبة العلوم الطبيعية',  'fr': 'Sciences Naturelles'},
    'T': {'ar': 'الشعبة التقنية',         'fr': 'Technique'},
    'A': {'ar': 'شعبة الآداب العصرية',   'fr': 'Lettres Modernes'},
    'O': {'ar': 'شعبة الفقه وأصوله',     'fr': 'Fiqh et Usul'},
}
SECONDARY_LEVELS = [5, 6, 7]   # مستويات الثانوي الموريتاني

# للتوافق الخلفي: الشعب القديمة (سيتم إخفاؤها من النموذج لكن تبقى في البيانات)
TRACKS = list(MAURITANIAN_TRACKS.keys())

def class_code(level, track, group=''):
    """ينتج رمز القسم: 5C  أو  5CA"""
    return f"{level}{track}{group.upper()}" if group else f"{level}{track}"

def class_display(level, track, group='', locale='ar'):
    """5C → '5C — شعبة الرياضيات'"""
    info = MAURITANIAN_TRACKS.get(track, {})
    name = info.get('fr' if locale == 'fr' else 'ar', track)
    grp  = f' ({group.upper()})' if group else ''
    return f"{level}{track}{grp} — {name}"

def parse_class_name(name):
    """
    يحلل اسم القسم ويرجع (level, track, group) للنظام الجديد
    أو None للنظام القديم (1AS2 ...)
    """
    import re as _re
    m = _re.match(r'^([567])([CDTAO])([A-Z]?)$', str(name).upper().strip())
    if m:
        return int(m.group(1)), m.group(2), m.group(3)
    return None
MONTHS = ['سبتمبر','أكتوبر','نوفمبر','ديسمبر','يناير','فبراير','مارس','أبريل','مايو','يونيو']

# ── قاعدة البيانات ─────────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')
# Neon.tech / Heroku يرسلان postgres:// — psycopg2 يحتاج postgresql://
DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
USE_PG = DATABASE_URL.startswith('postgresql://')

if USE_PG:
    import psycopg2, psycopg2.extras
    from psycopg2 import pool as pg_pool
    PH  = '%s'
    _PK = 'SERIAL PRIMARY KEY'
    _TS = 'NOW()::text'
    # Neon serverless: lazy pool — ينشأ عند أول طلب، لا عند الاستيراد
    _pg_pool = None

    def _get_pg_pool():
        global _pg_pool
        if _pg_pool is None or getattr(_pg_pool, 'closed', False):
            _pg_pool = pg_pool.ThreadedConnectionPool(
                1, 4, DATABASE_URL,
                connect_timeout=15,
                keepalives=1, keepalives_idle=30,
                keepalives_interval=5, keepalives_count=3,
            )
        return _pg_pool

    class _PooledConn:
        def __init__(self, conn, pool):
            self._conn = conn
            self._pool = pool
        def __getattr__(self, name):
            return getattr(self._conn, name)
        def close(self):
            # إعادة الاتصال للمجموعة فقط إذا كان مفتوحاً
            # الاتصال المغلق لا يُعاد للمجموعة (كان المنطق معكوساً سابقاً)
            if not self._conn.closed:
                self._pool.putconn(self._conn)
else:
    import sqlite3
    _DB_FILE = os.environ.get('DB_PATH', 'maarif.db')
    PH  = '?'
    _PK = 'INTEGER PRIMARY KEY AUTOINCREMENT'
    _TS = "datetime('now')"

def get_db():
    if USE_PG:
        pool = _get_pg_pool()
        conn = pool.getconn()
        # اتصال منتهي؟ أنشئ جديداً
        if conn.closed:
            pool.putconn(conn)
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=15)
        return _PooledConn(conn, pool)
    conn = sqlite3.connect(_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

# ── كاش بسيط في الذاكرة (TTL بالثواني) ─────────────────────────────

def _cache_get(key):
    now = time.time()
    execute("DELETE FROM kv_store WHERE expires_at < ?", (now,))
    row = query("SELECT v FROM kv_store WHERE k = ? AND expires_at >= ?", (key, now), one=True)
    if row:
        try:
            return json.loads(row['v'])
        except:
            return row['v']
    return None

def _cache_set(key, value, ttl=60):
    now = time.time()
    val_str = json.dumps(value, ensure_ascii=False)
    if USE_PG:
        execute("INSERT INTO kv_store (k, v, expires_at) VALUES (%s, %s, %s) ON CONFLICT (k) DO UPDATE SET v = EXCLUDED.v, expires_at = EXCLUDED.expires_at", (key, val_str, now + ttl))
    else:
        execute("INSERT INTO kv_store (k, v, expires_at) VALUES (?, ?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v, expires_at = excluded.expires_at", (key, val_str, now + ttl))

def _cache_del(prefix):
    if USE_PG:
        execute("DELETE FROM kv_store WHERE k LIKE %s", (prefix + '%',))
    else:
        execute("DELETE FROM kv_store WHERE k LIKE ?", (prefix + '%',))

def _to_dict(row):
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    return {k: row[k] for k in row.keys()}

def query(sql, args=(), one=False):
    sql = sql.replace('?', PH)
    conn = get_db()
    try:
        if USE_PG:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, args or None)
            rv = [dict(r) for r in cur.fetchall()]
        else:
            cur = conn.execute(sql, args)
            rv = [_to_dict(r) for r in cur.fetchall()]
        return (rv[0] if rv else None) if one else rv
    finally:
        conn.close()

def execute(sql, args=()):
    sql = sql.replace('?', PH)
    conn = get_db()
    try:
        if USE_PG:
            cur = conn.cursor()
            needs_returning = (
                sql.strip().upper().startswith('INSERT') and
                'RETURNING' not in sql.upper()
            )
            if needs_returning:
                sql = sql.rstrip().rstrip(';') + ' RETURNING id'
            cur.execute(sql, args or None)
            conn.commit()
            if needs_returning:
                row = cur.fetchone()
                return row[0] if row else None
            return None
        else:
            cur = conn.execute(sql, args)
            conn.commit()
            return cur.lastrowid
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def execute_bulk(sql, rows):
    if not rows:
        return
    sql = sql.replace('?', PH)
    conn = get_db()
    try:
        if USE_PG:
            cur = conn.cursor()
            cur.executemany(sql, rows)
        else:
            conn.executemany(sql, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def execute_script(stmts):
    conn = get_db()
    try:
        if USE_PG:
            cur = conn.cursor()
            for stmt in stmts:
                if stmt.strip():
                    cur.execute(stmt)
            conn.commit()
        else:
            conn.executescript(';\n'.join(stmts) + ';')
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ── مساعدات ─────────────────────────────────────────────────────────
def hash_pw(pw):
    return generate_password_hash(pw)

def avg_grade(grades_list):
    vals = [float(g['grade']) for g in grades_list if g.get('grade') is not None]
    return round(sum(vals) / len(vals), 2) if vals else None

def grade_label(avg):
    if avg is None: return '—'
    if avg >= 18: return 'ممتاز'
    if avg >= 16: return 'جيد جداً'
    if avg >= 14: return 'جيد'
    if avg >= 12: return 'مقبول'
    if avg >= 10: return 'ناجح'
    return 'راسب'

def _load_school_year(school_id):
    cfg = query('SELECT school_year FROM school_settings WHERE school_id=?',
                (school_id,), one=True)
    return (cfg['school_year'] if cfg and cfg.get('school_year') else CURRENT_YEAR)

def slug_from(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)

# ── اختصارات الجلسة ─────────────────────────────────────────────────
def sid():    return session.get('school_id')
def syear():  return session.get('school_year', CURRENT_YEAR)

# ── نظام الترجمة (مشترك مع app.py) ──────────────────────────────────
_translations_cache = {}

def _load_trans_cache():
    """تحميل ملفات الترجمة إلى الذاكرة مرة واحدة."""
    if _translations_cache:
        return
    lang_dir = os.path.join(os.path.dirname(__file__), 'translations')
    if os.path.exists(lang_dir):
        for fname in os.listdir(lang_dir):
            if fname.endswith('.json'):
                lang = fname.split('.')[0]
                try:
                    with open(os.path.join(lang_dir, fname), 'r', encoding='utf-8') as f:
                        _translations_cache[lang] = json.load(f)
                except Exception:
                    pass

def _(text):
    """ترجمة النص حسب اللغة الحالية في الجلسة."""
    lang = session.get('lang', 'ar')
    if lang == 'ar':
        return text
    _load_trans_cache()
    return _translations_cache.get(lang, {}).get(text, text)

# ── ديكوراتورز ──────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return dec

def school_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('school_id'):
            return redirect(url_for('super_admin.super_dashboard'))
        return f(*a, **kw)
    return dec

def admin_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if session.get('role') not in ('admin', 'super_admin'):
            flash('هذه الصفحة للمدير فقط', 'error')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a, **kw):
            if session.get('role') not in roles:
                flash('ليس لديك صلاحية للوصول لهذه الصفحة', 'error')
                return redirect(url_for('dashboard'))
            return f(*a, **kw)
        return dec
    return decorator

def no_supervisor(f):
    @wraps(f)
    def dec(*a, **kw):
        if session.get('role') == 'supervisor' and request.method == 'POST':
            flash('المراقب لا يملك صلاحية التعديل', 'error')
            return redirect(request.referrer or url_for('dashboard'))
        return f(*a, **kw)
    return dec

def super_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'super_admin':
            flash('هذه الصفحة لـ Super Admin فقط', 'error')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return dec

# ── DDL و تهيئة قاعدة البيانات ──────────────────────────────────────
_DDL = [
    f"""CREATE TABLE IF NOT EXISTS schools (
        id {_PK}, name TEXT NOT NULL, slug TEXT UNIQUE NOT NULL, plan TEXT DEFAULT 'basic', is_active INTEGER DEFAULT 1, max_students INTEGER DEFAULT 500, contact_email TEXT, contact_phone TEXT, address TEXT, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS users (
        id {_PK}, school_id INTEGER REFERENCES schools(id) ON DELETE CASCADE, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT DEFAULT 'teacher', subject_code TEXT, phone TEXT, email_verified INTEGER DEFAULT 0, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS classes (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, name TEXT NOT NULL, level TEXT NOT NULL, school_year TEXT DEFAULT '{CURRENT_YEAR}', sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS students (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, name TEXT NOT NULL, gender TEXT DEFAULT 'male', birth_date TEXT, phone TEXT, parent_name TEXT, parent_phone TEXT, receipt_number TEXT, class_id INTEGER REFERENCES classes(id), notes TEXT, is_active INTEGER DEFAULT 1, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS grades (
        id {_PK}, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE, subject_code TEXT NOT NULL, grade REAL, exam_type TEXT DEFAULT 'ordinary', school_year TEXT DEFAULT '{CURRENT_YEAR}', created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0, UNIQUE(student_id, subject_code, exam_type, school_year)
    )""",
    f"""CREATE TABLE IF NOT EXISTS attendance (
        id {_PK}, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE, month TEXT NOT NULL, absent_days INTEGER DEFAULT 0, school_year TEXT DEFAULT '{CURRENT_YEAR}', sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0, UNIQUE(student_id, month, school_year)
    )""",
    f"""CREATE TABLE IF NOT EXISTS fees (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, name TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, fee_type TEXT DEFAULT 'annual', school_year TEXT DEFAULT '{CURRENT_YEAR}', description TEXT, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS payments (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE, fee_id INTEGER REFERENCES fees(id) ON DELETE SET NULL, amount REAL NOT NULL DEFAULT 0, paid_at TEXT DEFAULT ({_TS}), receipt_number TEXT, notes TEXT, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS expenses (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, title TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0, category TEXT DEFAULT 'other', expense_date TEXT DEFAULT ({_TS}), notes TEXT, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS messages (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, sender_id INTEGER REFERENCES users(id) ON DELETE SET NULL, recipient_type TEXT DEFAULT 'broadcast', class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL, student_id INTEGER REFERENCES students(id) ON DELETE SET NULL, subject TEXT NOT NULL, body TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS homework (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, class_id INTEGER REFERENCES classes(id) ON DELETE CASCADE, subject_code TEXT, title TEXT NOT NULL, description TEXT, due_date TEXT, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS archives (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, title TEXT NOT NULL, school_year TEXT, students_count INTEGER DEFAULT 0, grades_count INTEGER DEFAULT 0, attendance_count INTEGER DEFAULT 0, payments_count INTEGER DEFAULT 0, data_json TEXT NOT NULL, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS school_settings (
        id {_PK}, school_id INTEGER UNIQUE REFERENCES schools(id) ON DELETE CASCADE, school_year TEXT DEFAULT '{CURRENT_YEAR}', phone TEXT, email TEXT, address TEXT, motto TEXT, updated_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
    f"""CREATE TABLE IF NOT EXISTS kv_store (
        k TEXT PRIMARY KEY,
        v TEXT NOT NULL,
        expires_at REAL
    )""",
    f"""CREATE TABLE IF NOT EXISTS timetable (
        id {_PK}, school_id INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE, class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE, teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, subject_code TEXT NOT NULL, day_of_week INTEGER NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL, created_at TEXT DEFAULT ({_TS}), sync_id TEXT UNIQUE, sync_status TEXT DEFAULT 'pending', last_modified TEXT DEFAULT ({_TS}), is_deleted INTEGER DEFAULT 0
    )""",
]

# ── نظام ترحيل البيانات (Migrations) ──────────────────────────────
_MIGRATIONS = [
    # يضمن وجود جدول timetable حتى لو لم ينجح execute_script في إنشائه
    ('001_create_timetable', f"""CREATE TABLE IF NOT EXISTS timetable (
        id {_PK},
        school_id  INTEGER NOT NULL REFERENCES schools(id)  ON DELETE CASCADE,
        class_id   INTEGER NOT NULL REFERENCES classes(id)  ON DELETE CASCADE,
        teacher_id INTEGER NOT NULL REFERENCES users(id)    ON DELETE CASCADE,
        subject_code TEXT NOT NULL,
        day_of_week  INTEGER NOT NULL,
        start_time   TEXT NOT NULL,
        end_time     TEXT NOT NULL,
        created_at   TEXT DEFAULT ({_TS}),
        is_deleted   INTEGER DEFAULT 0
    )"""),
    ('002_classes_structure_cycle',   "ALTER TABLE classes ADD COLUMN cycle   TEXT"),
    ('002_classes_structure_track',   "ALTER TABLE classes ADD COLUMN track   TEXT"),
    ('002_classes_structure_year',    "ALTER TABLE classes ADD COLUMN year    TEXT"),
    ('002_classes_structure_section', "ALTER TABLE classes ADD COLUMN section TEXT"),
    ('003_create_teacher_classes', f"""CREATE TABLE IF NOT EXISTS teacher_classes (
        id         {_PK},
        school_id  INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
        teacher_id INTEGER NOT NULL REFERENCES users(id)   ON DELETE CASCADE,
        class_id   INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
        UNIQUE(teacher_id, class_id)
    )"""),
    ('004_idx_students_school',    'CREATE INDEX IF NOT EXISTS idx_students_school    ON students(school_id)'),
    ('004_idx_grades_student',     'CREATE INDEX IF NOT EXISTS idx_grades_student     ON grades(student_id)'),
    ('004_idx_grades_year',        'CREATE INDEX IF NOT EXISTS idx_grades_year        ON grades(school_year)'),
    ('004_idx_attendance_student', 'CREATE INDEX IF NOT EXISTS idx_attendance_student ON attendance(student_id)'),
    ('004_idx_payments_school',    'CREATE INDEX IF NOT EXISTS idx_payments_school    ON payments(school_id)'),
    ('004_idx_classes_school',     'CREATE INDEX IF NOT EXISTS idx_classes_school     ON classes(school_id)'),
    ('005_login_attempts', f"""CREATE TABLE IF NOT EXISTS login_attempts (
        id        {_PK},
        email     TEXT NOT NULL,
        ip        TEXT,
        attempted_at TEXT DEFAULT ({_TS})
    )"""),
    ('006_term_grades', f"""CREATE TABLE IF NOT EXISTS term_grades (
        id           {_PK},
        school_id    INTEGER NOT NULL REFERENCES schools(id)  ON DELETE CASCADE,
        student_id   INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        subject_code TEXT NOT NULL,
        term         INTEGER NOT NULL,
        eval_type    TEXT NOT NULL,
        grade        REAL,
        school_year  TEXT NOT NULL,
        UNIQUE(student_id, subject_code, term, eval_type, school_year)
    )"""),
    ('007_class_subject_coefficients', f"""CREATE TABLE IF NOT EXISTS class_subject_coefficients (
        id           {_PK},
        school_id    INTEGER NOT NULL REFERENCES schools(id)  ON DELETE CASCADE,
        class_id     INTEGER NOT NULL REFERENCES classes(id)  ON DELETE CASCADE,
        subject_code TEXT NOT NULL,
        coefficient  REAL NOT NULL DEFAULT 1,
        school_year  TEXT NOT NULL,
        UNIQUE(class_id, subject_code, school_year)
    )"""),

    # ── نظام الدرجات الجديد (موريتانيا) ──────────────────────────────
    ('008_subjects', f"""CREATE TABLE IF NOT EXISTS subjects (
        id          {_PK},
        school_id   INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
        code        TEXT NOT NULL,
        name        TEXT NOT NULL,
        short_name  TEXT,
        UNIQUE(school_id, code)
    )"""),

    ('009_level_coefficients', f"""CREATE TABLE IF NOT EXISTS level_coefficients (
        id          {_PK},
        school_id   INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
        level_code  TEXT NOT NULL,
        subject_id  INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        coefficient REAL NOT NULL DEFAULT 1,
        UNIQUE(school_id, level_code, subject_id)
    )"""),

    ('010_grade_settings', f"""CREATE TABLE IF NOT EXISTS grade_settings (
        id                {_PK},
        school_id         INTEGER NOT NULL REFERENCES schools(id) ON DELETE CASCADE UNIQUE,
        tests_per_term    INTEGER NOT NULL DEFAULT 2,
        eval_weight       REAL NOT NULL DEFAULT 3,
        comp_weight       REAL NOT NULL DEFAULT 1,
        term1_weight      REAL NOT NULL DEFAULT 1,
        term2_weight      REAL NOT NULL DEFAULT 2,
        term3_weight      REAL NOT NULL DEFAULT 3
    )"""),

    ('011_classes_level_code',  "ALTER TABLE classes ADD COLUMN level_code    TEXT DEFAULT ''"),
    ('013_classes_group_letter',"ALTER TABLE classes ADD COLUMN group_letter TEXT DEFAULT ''"),
    ('013_classes_sec_level',   "ALTER TABLE classes ADD COLUMN sec_level    INTEGER"),
    ('014_students_name_fr',    "ALTER TABLE students ADD COLUMN name_fr TEXT DEFAULT ''"),
    ('015_login_lockouts', f"""CREATE TABLE IF NOT EXISTS login_lockouts (
        id           {_PK},
        email        TEXT NOT NULL,
        ip           TEXT NOT NULL,
        failed_count INTEGER NOT NULL DEFAULT 0,
        locked_until TEXT,
        last_attempt TEXT DEFAULT ({_TS}),
        UNIQUE(email, ip)
    )"""),

    ('012_new_term_grades', f"""CREATE TABLE IF NOT EXISTS new_term_grades (
        id           {_PK},
        school_id    INTEGER NOT NULL REFERENCES schools(id)      ON DELETE CASCADE,
        student_id   INTEGER NOT NULL REFERENCES students(id)     ON DELETE CASCADE,
        subject_id   INTEGER NOT NULL REFERENCES subjects(id)     ON DELETE CASCADE,
        term         INTEGER NOT NULL CHECK(term IN (1,2,3)),
        grade_type   TEXT NOT NULL,
        grade        REAL CHECK(grade >= 0 AND grade <= 20),
        school_year  TEXT NOT NULL,
        UNIQUE(student_id, subject_id, term, grade_type, school_year)
    )"""),

    # ── التحقق من البريد الإلكتروني ────────────────────────────────
    ('016_email_verification_columns', 'ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0'),
    ('017_email_verification_token',   'ALTER TABLE users ADD COLUMN verification_token TEXT'),
    ('018_email_token_expires',        'ALTER TABLE users ADD COLUMN token_expires_at TEXT'),
]

def run_migrations():
    # 1. إنشاء جدول التتبع إن لم يكن موجوداً
    execute(f"""CREATE TABLE IF NOT EXISTS schema_migrations (
        version TEXT PRIMARY KEY,
        applied_at TEXT DEFAULT ({_TS})
    )""")
    
    # 2. جلب التحديثات التي تم تطبيقها مسبقاً
    applied_rows = query("SELECT version FROM schema_migrations")
    applied = {r['version'] for r in applied_rows} if applied_rows else set()
    
    # 3. تطبيق التحديثات الجديدة فقط
    for version, sql in _MIGRATIONS:
        if version not in applied:
            print(f"⏳ جاري تطبيق التحديث: {version}...")
            try:
                execute(sql)
                if USE_PG:
                    execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                else:
                    execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                print(f"✅ تم تطبيق التحديث بنجاح: {version}")
            except Exception as e:
                error_msg = str(e).lower()
                # تجاوز الخطأ إذا كان العمود مضافاً مسبقاً (في حال قاعدة البيانات كانت جديدة)
                if 'duplicate column' in error_msg or 'already exists' in error_msg:
                    if USE_PG:
                        execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                    else:
                        execute("INSERT INTO schema_migrations (version) VALUES (?)", (version,))
                    print(f"✅ التحديث متخَطَّى (العمود موجود مسبقاً): {version}")
                else:
                    print(f"❌ فشل التحديث {version}: {e}")

# ── حساب المعادل العام ─────────────────────────────────────────────

def calc_subject_annual(student_id, subject_code, school_year):
    """
    المعدل السنوي لمادة واحدة:
      = (متوسط_فصل1×1 + متوسط_فصل2×2 + متوسط_فصل3×3 + متوسط_الاختبارات×3) / (1+2+3+3)
    كل فصل: متوسط امتحانيه | الاختبارات: متوسط جميع اختبارات السنة الستة
    """
    rows = query(
        "SELECT term, eval_type, grade FROM term_grades "
        "WHERE student_id=? AND subject_code=? AND school_year=?",
        (student_id, subject_code, school_year)
    )
    if not rows:
        return None

    tg = {(r['term'], r['eval_type']): r['grade'] for r in rows}

    weighted_sum = 0.0
    total_weight = 0.0

    for t in range(1, 4):
        e1 = tg.get((t, 'exam1'))
        e2 = tg.get((t, 'exam2'))
        if e1 is not None and e2 is not None:
            weighted_sum += ((e1 + e2) / 2) * t
            total_weight += t

    tests = [tg.get((t, typ)) for t in range(1, 4) for typ in ('test1', 'test2')]
    tests = [v for v in tests if v is not None]
    if tests:
        weighted_sum += (sum(tests) / len(tests)) * 3
        total_weight += 3

    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


def calc_general_average(student_id, school_year, class_id):
    """
    المعدل العام = مجموع(درجة_المادة × معامل_المادة) / مجموع_المعاملات
    """
    coeffs_rows = query(
        "SELECT subject_code, coefficient FROM class_subject_coefficients "
        "WHERE class_id=? AND school_year=?",
        (class_id, school_year)
    )
    coeffs = {code: 1.0 for code, _ in SUBJECTS}
    for r in coeffs_rows:
        coeffs[r['subject_code']] = r['coefficient']

    weighted_sum = 0.0
    total_coeff  = 0.0
    for code, _ in SUBJECTS:
        annual = calc_subject_annual(student_id, code, school_year)
        if annual is not None:
            c = coeffs.get(code, 1.0)
            weighted_sum += annual * c
            total_coeff  += c

    if total_coeff == 0:
        return None
    return round(weighted_sum / total_coeff, 2)


# ── نظام الدرجات الجديد (المعادلة الموريتانية) ─────────────────────

def get_grade_settings(school_id):
    """إعدادات الأوزان والدرجات لمدرسة معينة، مع قيم افتراضية."""
    row = query(
        "SELECT * FROM grade_settings WHERE school_id=?",
        (school_id,), one=True
    )
    if row:
        return dict(row)
    return {
        'tests_per_term': 2,
        'eval_weight': 3.0,
        'comp_weight': 1.0,
        'term1_weight': 1.0,
        'term2_weight': 2.0,
        'term3_weight': 3.0,
    }


def calc_term_average(student_id, subject_id, term, school_year, settings):
    """
    معدل المادة في فصل واحد:
      MOY_EVAL = متوسط الاختبارات
      MOY_COMP = درجة الامتحان الفصلي
      معدل_الفصل = (MOY_EVAL × eval_weight + MOY_COMP × comp_weight)
                   / (eval_weight + comp_weight)
    """
    rows = query(
        "SELECT grade_type, grade FROM new_term_grades "
        "WHERE student_id=? AND subject_id=? AND term=? AND school_year=?",
        (student_id, subject_id, term, school_year)
    )
    if not rows:
        return None

    grades = {r['grade_type']: r['grade'] for r in rows if r['grade'] is not None}

    # متوسط الاختبارات (test1 و test2 أو test1 فقط)
    test_vals = [grades[k] for k in ('test1', 'test2') if k in grades]
    moy_eval  = sum(test_vals) / len(test_vals) if test_vals else None

    # الامتحان الفصلي
    moy_comp = grades.get('exam')

    ew = settings.get('eval_weight', 3.0)
    cw = settings.get('comp_weight', 1.0)

    if moy_eval is not None and moy_comp is not None:
        return round((moy_eval * ew + moy_comp * cw) / (ew + cw), 2)
    elif moy_eval is not None:
        return round(moy_eval, 2)
    elif moy_comp is not None:
        return round(moy_comp, 2)
    return None


def calc_new_term_general(school_id, class_id, student_id, term, school_year):
    """
    المعدل العام للفصل:
      MOY_EVAL_GEN = Σ(متوسط_اختبارات_المادة × معاملها) / Σمعاملات
      MOY_COMP_GEN = Σ(امتحان_المادة × معاملها) / Σمعاملات
      MOY_GEN = (MOY_EVAL_GEN × eval_weight + MOY_COMP_GEN × comp_weight)
                / (eval_weight + comp_weight)
    """
    settings = get_grade_settings(school_id)
    ew = settings.get('eval_weight', 3.0)
    cw = settings.get('comp_weight', 1.0)

    # جلب المواد ومعاملاتها لهذا القسم/المستوى
    cls = query("SELECT level_code FROM classes WHERE id=?", (class_id,), one=True)
    level_code = cls['level_code'] if cls and cls.get('level_code') else ''

    coeffs_rows = query(
        "SELECT lc.subject_id, lc.coefficient FROM level_coefficients lc "
        "WHERE lc.school_id=? AND lc.level_code=?",
        (school_id, level_code)
    )

    if not coeffs_rows:
        return None

    sum_eval        = 0.0
    sum_comp        = 0.0
    total_coeff_eval = 0.0
    total_coeff_comp = 0.0

    for cr in coeffs_rows:
        sid_  = cr['subject_id']
        coeff = cr['coefficient']
        rows  = query(
            "SELECT grade_type, grade FROM new_term_grades "
            "WHERE student_id=? AND subject_id=? AND term=? AND school_year=?",
            (student_id, sid_, term, school_year)
        )
        grades = {r['grade_type']: r['grade'] for r in rows if r['grade'] is not None}

        test_vals = [grades[k] for k in ('test1', 'test2') if k in grades]
        moy_eval  = sum(test_vals) / len(test_vals) if test_vals else None
        moy_comp  = grades.get('exam')

        # كل جزء يُضاف فقط إذا كانت درجاته موجودة
        if moy_eval is not None:
            sum_eval        += moy_eval * coeff
            total_coeff_eval += coeff
        if moy_comp is not None:
            sum_comp        += moy_comp * coeff
            total_coeff_comp += coeff

    if total_coeff_eval == 0 and total_coeff_comp == 0:
        return None

    moy_eval_gen = sum_eval / total_coeff_eval if total_coeff_eval > 0 else None
    moy_comp_gen = sum_comp / total_coeff_comp if total_coeff_comp > 0 else None

    if moy_eval_gen is not None and moy_comp_gen is not None:
        moy_gen = (moy_eval_gen * ew + moy_comp_gen * cw) / (ew + cw)
    elif moy_eval_gen is not None:
        moy_gen = moy_eval_gen
    else:
        moy_gen = moy_comp_gen
    return round(moy_gen, 2)


def calc_annual_average(school_id, class_id, student_id, school_year):
    """
    المعدل السنوي المرجّح:
      (ف1×w1 + ف2×w2 + ف3×w3) / (w1+w2+w3)
    """
    settings = get_grade_settings(school_id)
    weights  = [
        settings.get('term1_weight', 1.0),
        settings.get('term2_weight', 2.0),
        settings.get('term3_weight', 3.0),
    ]

    weighted_sum = 0.0
    total_weight = 0.0

    for i, w in enumerate(weights, start=1):
        avg = calc_new_term_general(school_id, class_id, student_id, i, school_year)
        if avg is not None:
            weighted_sum += avg * w
            total_weight += w

    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 2)


def get_level_subjects(school_id, level_code):
    """قائمة مواد مستوى معين مع معاملاتها."""
    return query(
        "SELECT s.id, s.code, s.name, s.short_name, lc.coefficient "
        "FROM level_coefficients lc "
        "JOIN subjects s ON s.id = lc.subject_id "
        "WHERE lc.school_id=? AND lc.level_code=? "
        "ORDER BY lc.coefficient DESC, s.name",
        (school_id, level_code)
    )


def init_default_subjects(school_id):
    """إضافة المواد والمعاملات الافتراضية للنظام الموريتاني إذا لم تكن موجودة."""
    existing = query("SELECT COUNT(*) as c FROM subjects WHERE school_id=?", (school_id,), one=True)
    if existing and existing['c'] > 0:
        return

    default_subjects = [
        ('AR',  'اللغة العربية',        'عربية'),
        ('FR',  'اللغة الفرنسية',       'فرنسية'),
        ('AN',  'اللغة الإنجليزية',     'إنجليزية'),
        ('MA',  'الرياضيات',            'رياضيات'),
        ('SN',  'العلوم الطبيعية',      'علوم'),
        ('PC',  'الفيزياء والكيمياء',   'فيزياء'),
        ('IR',  'التربية الإسلامية',    'إسلامية'),
        ('IC',  'التربية المدنية',      'مدنية'),
        ('HG',  'التاريخ والجغرافيا',   'تاريخ'),
        ('INF', 'المعلوماتية',          'معلوماتية'),
        ('SP',  'التربية البدنية',      'رياضة'),
        ('PH',  'التربية البدنية والرياضة', 'رياضة+'),
    ]

    default_levels = {
        '1AS': [('AR',5),('FR',4),('AN',2),('MA',6),('SN',2),('IR',3),('IC',1),('HG',1),('INF',2),('SP',1)],
        '2AS': [('AR',5),('FR',4),('AN',2),('MA',6),('SN',2),('IR',3),('IC',1),('HG',1),('INF',2),('SP',1)],
        '3AS': [('AR',5),('FR',4),('AN',2),('MA',6),('SN',2),('IR',3),('IC',1),('HG',1),('INF',2),('SP',1)],
        '4AS': [('AR',5),('FR',4),('AN',2),('MA',6),('SN',2),('IR',3),('IC',1),('HG',1),('INF',2),('SP',1)],
        '5C':  [('AR',3),('FR',3),('AN',2),('MA',6),('SN',3),('PC',5),('IR',2),('IC',1),('HG',2),('PH',2),('SP',1)],
        '6C':  [('AR',2),('FR',2),('AN',2),('MA',7),('SN',3),('PC',6),('IR',2),('IC',1),('HG',2),('PH',2),('SP',1)],
        '7D':  [('AR',2),('FR',2),('AN',2),('MA',6),('SN',8),('PC',7),('IR',2),('SP',1)],
    }

    # إدراج المواد
    subj_ids = {}
    for code, name, short in default_subjects:
        execute(
            "INSERT OR IGNORE INTO subjects(school_id,code,name,short_name) VALUES(?,?,?,?)",
            (school_id, code, name, short)
        )
        row = query("SELECT id FROM subjects WHERE school_id=? AND code=?", (school_id, code), one=True)
        if row:
            subj_ids[code] = row['id']

    # إدراج المعاملات
    for level_code, items in default_levels.items():
        for code, coeff in items:
            if code in subj_ids:
                execute(
                    "INSERT OR IGNORE INTO level_coefficients(school_id,level_code,subject_id,coefficient) "
                    "VALUES(?,?,?,?)",
                    (school_id, level_code, subj_ids[code], coeff)
                )


def init_db():
    execute_script(_DDL)
    run_migrations()  # تشغيل فاحص التحديثات عند بدء التطبيق

    sa_email  = os.environ.get('SUPER_ADMIN_EMAIL')
    sa_pw_raw = os.environ.get('SUPER_ADMIN_PASSWORD')
    sa_name   = os.environ.get('SUPER_ADMIN_NAME', 'ballak')

    if not sa_email or not sa_pw_raw:
        print('⚠️  SUPER_ADMIN_EMAIL أو SUPER_ADMIN_PASSWORD غير مضبوطَين — اضبطهما في ملف .env')
        return

    sa_pw = hash_pw(sa_pw_raw)
    if USE_PG:
        execute("""
            INSERT INTO users (school_id, name, email, password, role, email_verified)
            VALUES (NULL, %s, %s, %s, 'super_admin', 1)
            ON CONFLICT (email) DO UPDATE SET password=EXCLUDED.password, name=EXCLUDED.name, email_verified=1
        """, (sa_name, sa_email, sa_pw))
    else:
        execute("""
            INSERT INTO users (school_id, name, email, password, role, email_verified)
            VALUES (NULL, ?, ?, ?, 'super_admin', 1)
            ON CONFLICT(email) DO UPDATE SET password=excluded.password, name=excluded.name, email_verified=1
        """, (sa_name, sa_email, sa_pw))

    if USE_PG:
        print('✅ DB: PostgreSQL')
    else:
        print('✅ DB: SQLite')