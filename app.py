"""
═══════════════════════════════════════════════════════════════════
  مدرستي — نظام إدارة المدارس متعدد المستأجرين
  Multi-Tenant School Management System
  Flask + PostgreSQL (Railway) / SQLite (Dev)
═══════════════════════════════════════════════════════════════════
"""
import os, hashlib, json, datetime
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash)
from werkzeug.security import generate_password_hash, check_password_hash

from utils import (
    CURRENT_YEAR, SUBJECTS, MONTHS, USE_PG,
    query, execute, execute_bulk,
    _cache_get, _cache_set, _cache_del,
    hash_pw, avg_grade, grade_label, _load_school_year, sid, syear,
    school_required, admin_required, role_required,
    init_db, calc_subject_annual, calc_general_average,
    MAURITANIAN_TRACKS, SECONDARY_LEVELS, parse_class_name,
)

# ── استيراد الـ Blueprints ────────────────────────────────────────
from blueprints.academic import academic_bp
from blueprints.accounting import accounting_bp
from blueprints.communication import communication_bp
from blueprints.super_admin import super_admin_bp
from blueprints.tools import tools_bp
from blueprints.sync import sync_bp

# ── دوال التحويل والتنسيق ────────────────────────────────────────────
def ensure_latin_digits(value):
    """
    تحويل جميع الأرقام إلى اللاتينية (0-9) بدون استثناء
    تطبق على الأرقام العربية والفارسية والأردية
    مثال:
        - ٠١٢٣٤٥٦٧٨٩ → 0123456789
        - ۰۱۲۳۴۵۶۷۸۹ → 0123456789
    """
    if value is None:
        return value
    
    value = str(value)
    # خريطة تحويل شاملة للأرقام العربية والفارسية إلى اللاتينية
    arabic_to_latin = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
    return value.translate(arabic_to_latin)

# ── إعداد التطبيق ──────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'maarif-dev-key-set-SECRET_KEY-in-production')
app.jinja_env.filters['enumerate'] = enumerate

# فرض الأرقام اللاتينية تلقائيا على جميع المخرجات
original_finalize = app.jinja_env.finalize or (lambda x: x)
def finalize_with_latin_digits(value):
    """تطبيق تحويل الأرقام على كل المخرجات تلقائيا"""
    result = original_finalize(value)
    return ensure_latin_digits(result)

app.jinja_env.finalize = finalize_with_latin_digits

# ── CSRF Protection Helper ─────────────────────────────────────────
def generate_csrf_token():
    """Generate a CSRF token for the session."""
    if '_csrf_token' not in session:
        session['_csrf_token'] = os.urandom(24).hex()
    return session['_csrf_token']

def verify_csrf_token(token):
    """Verify CSRF token from request."""
    return token == session.get('_csrf_token')

@app.before_request
def csrf_protect():
    """Verify CSRF token on POST/PUT/DELETE requests."""
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        # Skip CSRF for API endpoints starting with /api/
        if not request.path.startswith('/api/'):
            token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not token or not verify_csrf_token(token):
                return jsonify(status='error', message='CSRF token invalid'), 403

@app.context_processor
def inject_csrf_token():
    return dict(csrf_token=generate_csrf_token)

# ── تأمين التطبيق (Security Configurations) ────────────────────────
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # الحد الأقصى للملفات المرفوعة 10 ميجابايت (حماية من DoS)
app.config['SESSION_COOKIE_SECURE'] = USE_PG         # تفعيل الكوكيز الآمنة في الإنتاج فقط (يتطلب HTTPS)
app.config['SESSION_COOKIE_HTTPONLY'] = True         # منع الجافاسكربت من سرقة الجلسة (حماية من XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'        # حماية قوية من هجمات تزوير الطلبات (CSRF)

@app.after_request
def secure_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'        # حماية من Clickjacking (يمنع وضع الموقع في iframe)
    response.headers['X-Content-Type-Options'] = 'nosniff'    # منع المتصفح من تخمين نوع الملفات
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains' # إجبار استخدام HTTPS
    return response

# ── نظام الترجمة — يُستخدم _ من utils لمشاركتها مع البلوبرنتات ──────
from utils import _, _load_trans_cache, _translations_cache

def load_translations():
    _load_trans_cache()

load_translations()

def get_locale():
    return session.get('lang', 'ar')

@app.context_processor
def inject_i18n():
    lang = get_locale()
    _load_trans_cache()
    return {
        'current_translations': _translations_cache.get(lang, {}),
        'is_rtl': lang not in ('en', 'fr', 'tr'),
        'ensure_latin_digits': ensure_latin_digits,  # جعلها متاحة في كل القوالب
    }

def sub_digits(s):
    """تحويل الأرقام بعد AS إلى مصغرات unicode — مثلاً 1AS2 → 1AS₂"""
    s = ensure_latin_digits(s)  # تأكد من الأرقام اللاتينية أولا
    s = str(s)
    if 'AS' not in s:
        return s
    prefix, _, suffix = s.partition('AS')
    sub = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
    return prefix + 'AS' + suffix.translate(sub)

# تطبيق المرشح على جميع المخرجات تلقائيا
@app.template_filter('latin_digits')
def filter_latin_digits(value):
    """مرشح Jinja2 لتحويل الأرقام إلى لاتينية"""
    return ensure_latin_digits(value)

def translate_role(role):
    """ترجمة الدور بناءً على اللغة الحالية"""
    lang = get_locale()
    roles_dict = {
        'super_admin': {
            'ar': 'مشرف عام',
            'en': 'General Administrator',
            'fr': 'Administrateur Général',
            'tr': 'Genel Yönetici'
        },
        'admin': {
            'ar': 'مدير',
            'en': 'Administrator',
            'fr': 'Administrateur',
            'tr': 'Yönetici'
        },
        'teacher': {
            'ar': 'معلم',
            'en': 'Teacher',
            'fr': 'Enseignant',
            'tr': 'Öğretmen'
        },
        'staff': {
            'ar': 'موظف',
            'en': 'Staff',
            'fr': 'Personnel',
            'tr': 'Personel'
        },
        'accountant': {
            'ar': 'محاسب',
            'en': 'Accountant',
            'fr': 'Comptable',
            'tr': 'Muhasebeci'
        },
        'supervisor': {
            'ar': 'مراقب',
            'en': 'Supervisor',
            'fr': 'Superviseur',
            'tr': 'Süpervizör'
        }
    }
    return roles_dict.get(role, {}).get(lang, role)

app.jinja_env.globals.update(_=_, get_locale=get_locale, enumerate=enumerate, dict=dict, len=len,
                             sub_digits=sub_digits, parse_class_name=parse_class_name,
                             MAURITANIAN_TRACKS=MAURITANIAN_TRACKS,
                             ensure_latin_digits=ensure_latin_digits, translate_role=translate_role)

# ── تسجيل الـ Blueprints ──────────────────────────────────────────
app.register_blueprint(academic_bp)
app.register_blueprint(accounting_bp)
app.register_blueprint(communication_bp)
app.register_blueprint(super_admin_bp)
app.register_blueprint(tools_bp)
app.register_blueprint(sync_bp)

@app.route('/set_lang/<lang>')
def set_lang(lang):
    if lang in ['ar', 'en', 'fr', 'tr']:
        session['lang'] = lang
    return redirect(request.referrer or url_for('login'))
# ─────────────────────────────────────────────────────────────────

# ── نظام التحقق من البريد الإلكتروني ────────────────────────────────
import secrets
from datetime import timedelta

def generate_verification_token():
    """توليد رمز تحقق عشوائي"""
    return secrets.token_urlsafe(32)

def send_verification_email(user_email, user_name, verification_token):
    """
    إرسال رسالة تحقق من البريد الإلكتروني
    ملاحظة: في الإنتاج، استخدم SendGrid أو AWS SES
    في التطوير، نطبعها في السجل فقط
    """
    try:
        # محاولة الحصول على الـ host URL من السياق الحالي
        if request:
            verification_url = f"{request.host_url.rstrip('/')}/verify-email/{verification_token}"
        else:
            verification_url = f"http://localhost:5000/verify-email/{verification_token}"
    except RuntimeError:
        # خارج سياق الطلب (مثل الاختبارات)
        verification_url = f"http://localhost:5000/verify-email/{verification_token}"
    
    email_body = f"""
مرحباً {user_name}،

لتأكيد حسابك في مدرستي، اضغط على الرابط أدناه:
{verification_url}

ينتهي الرابط بعد 24 ساعة.

مع تحياتنا،
فريق مدرستي
    """
    
    # في التطوير: طباعة الرابط في السجل
    print(f"\n{'='*60}")
    print(f"📧 رسالة تحقق للبريد: {user_email}")
    print(f"{'='*60}")
    print(f"الاسم: {user_name}")
    print(f"الرابط: {verification_url}")
    print(f"{'='*60}\n")
    
    # في الإنتاج، يمكن استخدام:
    # import smtplib
    # from email.mime.text import MIMEText
    # msg = MIMEText(email_body, 'plain', 'utf-8')
    # msg['Subject'] = 'تأكيد البريد الإلكتروني'
    # msg['From'] = 'noreply@maarif.school'
    # msg['To'] = user_email
    # smtplib.SMTP('smtp.sendgrid.net', 587).sendmail(...)
    
    return True

@app.route('/verify-email/<token>')
def verify_email(token):
    """التحقق من البريد الإلكتروني باستخدام الرمز"""
    if not token:
        flash('رمز التحقق غير صحيح', 'error')
        return redirect(url_for('login'))
    
    user = query(
        'SELECT * FROM users WHERE verification_token=?',
        (token,), one=True
    )
    
    if not user:
        flash('رمز التحقق غير موجود', 'error')
        return redirect(url_for('login'))
    
    # التحقق من انتهاء صلاحية الرمز
    if user.get('token_expires_at'):
        try:
            expires_at = datetime.datetime.fromisoformat(str(user['token_expires_at']))
            if datetime.datetime.utcnow() > expires_at:
                flash('انتهت صلاحية رمز التحقق. اطلب رابط تحقق جديد', 'error')
                return redirect(url_for('login'))
        except Exception:
            pass
    
    # تحديث البريد المؤكد
    execute(
        'UPDATE users SET email_verified=1, verification_token=NULL, token_expires_at=NULL WHERE id=?',
        (user['id'],)
    )
    
    flash('✅ تم تأكيد البريد الإلكتروني بنجاح! يمكنك الآن تسجيل الدخول', 'success')
    return redirect(url_for('login'))

@app.route('/resend-verification/<int:user_id>', methods=['POST'])
@school_required
@admin_required
def resend_verification(user_id):
    """إعادة إرسال رابط التحقق من البريد"""
    user = query('SELECT * FROM users WHERE id=? AND school_id=?', (user_id, sid()), one=True)
    
    if not user:
        return jsonify({'success': False, 'message': 'المستخدم غير موجود'}), 404
    
    if user.get('email_verified'):
        return jsonify({'success': False, 'message': 'البريد مؤكد بالفعل'}), 400
    
    token = generate_verification_token()
    expires_at = (datetime.datetime.utcnow() + timedelta(hours=24)).isoformat()
    
    execute(
        'UPDATE users SET verification_token=?, token_expires_at=? WHERE id=?',
        (token, expires_at, user['id'])
    )
    
    send_verification_email(user['email'], user['name'], token)
    
    return jsonify({'success': True, 'message': 'تم إرسال رابط التحقق إلى البريد الإلكتروني'})



# ════════════════════════════════════════════════════════════════════
#  تسجيل الدخول / الخروج
# ════════════════════════════════════════════════════════════════════

@app.route('/', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        if session.get('role') == 'super_admin':
            return redirect(url_for('super_admin.super_dashboard'))
        return redirect(url_for('dashboard'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        pw_input = request.form.get('password', '')

        # ✅ SECURITY: Brute-Force Protection (rate limiting per email)
        lock_row = query(
            "SELECT failed_count, locked_until FROM login_lockouts WHERE email=?",
            (email,), one=True
        )
        if lock_row and lock_row.get('locked_until'):
            lu = lock_row['locked_until']
            try:
                locked_until = lu if isinstance(lu, datetime.datetime) else datetime.datetime.fromisoformat(str(lu))
                locked_until = locked_until.replace(tzinfo=None)
                now = datetime.datetime.utcnow()
                if locked_until > now:
                    wait_secs = max(1, int((locked_until - now).total_seconds()))
                    wait_mins = (wait_secs + 59) // 60
                    error = f'🔒 الحساب مقفل مؤقتاً لأسباب أمنية. يرجى الانتظار {wait_mins} دقيقة.'
                    return render_template('login.html', error=error)
            except Exception:
                pass

        user  = query('SELECT * FROM users WHERE email=?', (email,), one=True)

        if user:
            is_valid = check_password_hash(user['password'], pw_input)

            # الترقية التلقائية للتشفير القديم (Seamless Hash Upgrade)
            if not is_valid:
                old_hash = hashlib.sha256(pw_input.encode()).hexdigest()
                if old_hash == user['password']:
                    is_valid = True
                    new_hash = generate_password_hash(pw_input)
                    execute('UPDATE users SET password=? WHERE id=?', (new_hash, user['id']))

            if is_valid:
                # ── التحقق من تأكيد البريد الإلكتروني ──────────────────
                # نطبّق الحجب فقط على المستخدمين الذين مرّوا بمسار التحقق فعلاً
                # (لديهم token) — المستخدمون القدامى أو الإداريون لا يُحجبون
                needs_verification = (
                    not user.get('email_verified')
                    and user.get('verification_token')       # أُرسل له token فعلاً
                    and user.get('role') not in ('admin', 'super_admin', 'accountant')
                )
                if needs_verification:
                    error = '⚠️ يجب تأكيد بريدك الإلكتروني أولاً. تحقق من رسائلك البريدية.'
                    flash(error, 'warning')
                    return render_template('login.html', error=error)

                # تسجيل دخول ناجح: إعادة تعيين العداد
                execute("DELETE FROM login_lockouts WHERE email=?", (email,))

                session['user_id']   = user['id']
                session['user_name'] = user['name']
                session['role']      = user['role']
                session['subject']   = user['subject_code']
                session['school_id'] = user['school_id']

                if user['role'] == 'super_admin':
                    session['school_name'] = None
                    return redirect(url_for('super_admin.super_dashboard'))

                school = query('SELECT * FROM schools WHERE id=?', (user['school_id'],), one=True)
                if school and not school['is_active']:
                    session.clear()
                    error = 'حساب المدرسة معلّق. تواصل مع الدعم.'
                elif school:
                    session['school_name'] = school['name']
                    session['school_year'] = _load_school_year(user['school_id'])
                    # للمعلم: احفظ القسم المرتبط به من teacher_classes
                    if user['role'] == 'teacher':
                        tc = query(
                            'SELECT class_id FROM teacher_classes WHERE teacher_id=? AND school_id=? LIMIT 1',
                            (user['id'], user['school_id']), one=True)
                        session['class_id'] = tc['class_id'] if tc else None
                    if user['role'] == 'accountant':
                        return redirect(url_for('accounting.accounting'))
                    return redirect(url_for('dashboard'))
                else:
                    session.clear()
                    error = 'المدرسة غير موجودة.'
            else:
                # تسجيل محاولة فاشلة وحساب مهلة الانتظار
                prev_count = lock_row['failed_count'] if lock_row else 0
                new_count  = prev_count + 1

                if new_count < 5:
                    lock_mins = 0
                elif new_count == 5:
                    lock_mins = 2
                else:
                    lock_mins = 5 * (new_count - 5)

                now     = datetime.datetime.utcnow()
                now_str = now.strftime('%Y-%m-%d %H:%M:%S')
                locked_until_str = (
                    (now + datetime.timedelta(minutes=lock_mins)).strftime('%Y-%m-%d %H:%M:%S')
                    if lock_mins else None
                )

                # ✅ SECURITY: Use email ONLY (not email+ip) for rate limiting
                if lock_row:
                    execute(
                        "UPDATE login_lockouts SET failed_count=?, locked_until=?, last_attempt=? WHERE email=?",
                        (new_count, locked_until_str, now_str, email)
                    )
                else:
                    execute(
                        "INSERT INTO login_lockouts(email, failed_count, locked_until, last_attempt) VALUES(?,?,?,?)",
                        (email, new_count, locked_until_str, now_str)
                    )

                remaining = 5 - new_count
                if lock_mins:
                    error = f'🔐 محاولات متعددة فاشلة. تم قفل الحساب لمدة {lock_mins} دقيقة.'
                elif remaining > 0:
                    error = f'البريد الإلكتروني أو كلمة المرور غير صحيحة. ({remaining} محاولة متبقية)'
                else:
                    error = 'البريد الإلكتروني أو كلمة المرور غير صحيحة'
        else:
            error = 'البريد الإلكتروني أو كلمة المرور غير صحيحة'

    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ════════════════════════════════════════════════════════════════════
#  لوحة تحكم المدرسة
# ════════════════════════════════════════════════════════════════════

@app.route('/dashboard')
@school_required
def dashboard():
    school_id   = sid()
    school_year = syear()
    cache_key   = f'dash:{school_id}:{school_year}'

    cached = _cache_get(cache_key)
    if cached:
        stats, classes, top_stus, grade_dist = cached
    else:
        # 1 query instead of 3 separate COUNT queries
        counts = query("""
            SELECT
                (SELECT COUNT(*) FROM students WHERE school_id=? AND is_active=1) as students,
                (SELECT COUNT(*) FROM classes  WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL)) as classes,
                (SELECT COUNT(*) FROM users    WHERE school_id=? AND role='teacher' AND (is_deleted=0 OR is_deleted IS NULL)) as teachers
        """, (school_id, school_id, school_id), one=True)
        stats = {
            'students': counts['students'] or 0,
            'classes':  counts['classes']  or 0,
            'teachers': counts['teachers'] or 0,
            'passing':  0,
        }

        # passing rate — filter to summary grades only
        avgs = query("""
            SELECT s.id, AVG(g.grade) as avg FROM students s
            JOIN grades g ON g.student_id=s.id
            WHERE s.school_id=? AND g.school_year=?
              AND g.exam_type IN ('avg','ordinary')
            GROUP BY s.id
        """, (school_id, school_year))
        if avgs:
            passing = sum(1 for a in avgs if a['avg'] and a['avg'] >= 10)
            stats['passing'] = round(passing / len(avgs) * 100)

        classes = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY level, name', (school_id,))

        # top student per class — 1 query, then pick best per class in Python
        top_rows = query("""
            SELECT s.name, s.class_id, AVG(g.grade) as avg
            FROM students s
            JOIN grades g ON g.student_id=s.id
            WHERE s.school_id=? AND s.is_active=1 AND g.school_year=?
              AND g.exam_type IN ('avg','ordinary')
            GROUP BY s.id, s.class_id
            ORDER BY s.class_id, avg DESC
        """, (school_id, school_year))
        cls_id_to_name = {c['id']: c['name'] for c in classes}
        seen_cls = set()
        top_stus = []
        for r in top_rows:
            cid = r['class_id']
            if cid in seen_cls or not r['avg']:
                continue
            seen_cls.add(cid)
            top_stus.append({'class': cls_id_to_name.get(cid, ''),
                              'name': r['name'],
                              'avg':  round(r['avg'], 2)})
            if len(top_stus) == 3:
                break

        # إضافة بيانات الرسوم البيانية: توزيع الدرجات
        grade_dist = query("""
            SELECT
                CASE
                    WHEN grade >= 16 THEN 'ممتاز'
                    WHEN grade >= 12 THEN 'جيد'
                    WHEN grade >= 10 THEN 'مقبول'
                    ELSE 'راسب'
                END as label, COUNT(*) as count
            FROM grades
            WHERE school_year=?
              AND student_id IN (SELECT id FROM students WHERE school_id=?)
            GROUP BY label
        """, (school_year, school_id))

        _cache_set(cache_key, (stats, classes, top_stus, grade_dist), ttl=60)

    return render_template('dashboard.html', stats=stats, classes=classes,
                           top_students=top_stus,
                           grade_dist=grade_dist,
                           school=session.get('school_name', ''),
                           year=school_year,
                           is_impersonating=bool(session.get('_super_admin_id')))


# ── الدرجات ────────────────────────────────────────────────────────
@app.route('/grades')
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def grades_page():
    # المعلم يرى مادته فقط
    teacher_subject = session['subject'] if session.get('role') == 'teacher' else None
    classes  = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY level,name', (sid(),))
    class_id = request.args.get('class_id', '')
    students_data = []
    sel_class = None
    if class_id:
        sel_class = query('SELECT * FROM classes WHERE id=? AND school_id=?',
                          (class_id, sid()), one=True)
        if sel_class:
            students = query(
                'SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name',
                (class_id,))
            for stu in students:
                gs   = query('SELECT * FROM grades WHERE student_id=? AND school_year=?',
                             (stu['id'], syear()))
                # المعلم يرى درجات مادته فقط
                if teacher_subject:
                    gs = [g for g in gs if g['subject_code'] == teacher_subject]
                gmap = {g['subject_code']: g['grade'] for g in gs}
                av   = avg_grade(gs)
                students_data.append({
                    'id': stu['id'], 'name': stu['name'],
                    'grades': gmap, 'avg': av,
                    'label': grade_label(av),
                    'pass': av is not None and av >= 10,
                })
            students_data.sort(key=lambda x: x['avg'] or 0, reverse=True)
            for i, s in enumerate(students_data):
                s['rank'] = i + 1
    # المعلم يرى المواد المتاحة له فقط
    visible_subjects = [(c, n) for c, n in SUBJECTS if not teacher_subject or c == teacher_subject]
    return render_template('grades.html', classes=classes, students_data=students_data,
                           sel_class=sel_class, subjects=visible_subjects, class_id=class_id)


@app.route('/grades/save', methods=['POST'])
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def save_grades():
    data   = request.get_json()
    grades = data.get('grades', [])
    # المعلم لا يستطيع حفظ درجات مادة غير مادته
    if session.get('role') == 'teacher':
        own = session.get('subject')
        grades = [g for g in grades if g.get('subject_code') == own]
    sql = """
        INSERT INTO grades(student_id,subject_code,grade,exam_type,school_year)
        VALUES(?,?,?,'ordinary',?)
        ON CONFLICT(student_id,subject_code,exam_type,school_year)
        DO UPDATE SET grade=excluded.grade
    """
    for g in grades:
        grade_val = g.get('grade')
        if grade_val is not None and not (0 <= float(grade_val) <= 20):
            return jsonify({'ok': False, 'error': f'قيمة الدرجة غير صالحة: {grade_val}'}), 400
    rows = [(g['student_id'], g['subject_code'], g['grade'], syear()) for g in grades]
    execute_bulk(sql, rows)
    _cache_del(f'dash:{sid()}:')
    return jsonify({'ok': True, 'saved': len(rows)})


# ── درجات الفصول (النظام الجديد) ───────────────────────────────────
@app.route('/grades/term')
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def term_grades_page():
    from utils import get_grade_settings, get_level_subjects
    classes  = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY level,name', (sid(),))
    class_id = request.args.get('class_id', '')
    term     = request.args.get('term', '1')
    subj_id  = request.args.get('subject_id', '')
    gs       = get_grade_settings(sid())

    sel_class = None
    subjects  = []
    students_data = []
    sel_subject = None

    if class_id:
        sel_class = query('SELECT * FROM classes WHERE id=? AND school_id=?', (class_id, sid()), one=True)
        if sel_class:
            level_code = sel_class.get('level_code', '')
            subjects   = get_level_subjects(sid(), level_code)
            if subj_id:
                sel_subject = next((s for s in subjects if str(s['id']) == str(subj_id)), None)
                students = query('SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name', (class_id,))
                for stu in students:
                    tgs  = query(
                        "SELECT grade_type, grade FROM new_term_grades "
                        "WHERE student_id=? AND subject_id=? AND term=? AND school_year=?",
                        (stu['id'], subj_id, int(term), syear())
                    )
                    gmap = {r['grade_type']: r['grade'] for r in tgs}
                    students_data.append({'id': stu['id'], 'name': stu['name'], 'grades': gmap})

    return render_template('term_grades.html',
        classes=classes, sel_class=sel_class,
        class_id=class_id, term=term, subject_id=subj_id,
        subjects=subjects, sel_subject=sel_subject,
        students_data=students_data, gs=gs)


@app.route('/grades/term/save', methods=['POST'])
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def save_term_grades():
    data       = request.get_json()
    entries    = data.get('grades', [])
    term       = int(data.get('term', 1))
    subject_id = data.get('subject_id', '')

    sql = """
        INSERT INTO new_term_grades(school_id, student_id, subject_id, term, grade_type, grade, school_year)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(student_id, subject_id, term, grade_type, school_year)
        DO UPDATE SET grade=excluded.grade
    """
    rows = []
    for entry in entries:
        grade_val = entry.get('grade')
        if grade_val is not None and str(grade_val).strip() != '':
            try:
                fv = float(grade_val)
                if not (0 <= fv <= 20):
                    return jsonify({'ok': False, 'error': f'قيمة الدرجة غير صالحة: {grade_val}'}), 400
            except (ValueError, TypeError):
                return jsonify({'ok': False, 'error': f'قيمة الدرجة غير صالحة: {grade_val}'}), 400
            rows.append((sid(), entry['student_id'], subject_id, term, entry['grade_type'], fv, syear()))

    execute_bulk(sql, rows)
    _cache_del(f'dash:{sid()}:')
    return jsonify({'ok': True, 'saved': len(rows)})


# ── المعدل العام (النظام الجديد) ────────────────────────────────────
@app.route('/grades/annual')
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def annual_grades_page():
    from utils import get_level_subjects, calc_annual_average, calc_new_term_general, get_grade_settings
    classes  = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY level,name', (sid(),))
    class_id = request.args.get('class_id', '')
    sel_class     = None
    students_data = []
    subjects      = []
    gs            = get_grade_settings(sid())

    if class_id:
        sel_class = query('SELECT * FROM classes WHERE id=? AND school_id=?', (class_id, sid()), one=True)
        if sel_class:
            level_code = sel_class.get('level_code', '')
            subjects   = get_level_subjects(sid(), level_code)
            students   = query('SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name', (class_id,))
            for stu in students:
                # معدل كل فصل
                term_avgs = []
                for t in [1, 2, 3]:
                    ta = calc_new_term_general(sid(), class_id, stu['id'], t, syear())
                    term_avgs.append(ta)
                # المعدل السنوي المرجّح
                annual = calc_annual_average(sid(), class_id, stu['id'], syear())
                students_data.append({
                    'id': stu['id'], 'name': stu['name'],
                    'term1': term_avgs[0], 'term2': term_avgs[1], 'term3': term_avgs[2],
                    'avg': annual,
                    'label': grade_label(annual),
                    'pass': annual is not None and annual >= 10,
                })
            students_data.sort(key=lambda x: x['avg'] or 0, reverse=True)
            for i, s in enumerate(students_data):
                s['rank'] = i + 1

    return render_template('annual_grades.html',
        classes=classes, sel_class=sel_class,
        class_id=class_id, students_data=students_data,
        subjects=subjects, gs=gs)


# ── معاملات المواد ──────────────────────────────────────────────────
@app.route('/grades/coefficients/<int:class_id>', methods=['GET', 'POST'])
@school_required
@admin_required
def class_coefficients(class_id):
    cls = query('SELECT * FROM classes WHERE id=? AND school_id=?', (class_id, sid()), one=True)
    if not cls:
        flash(_('القسم غير موجود'), 'error')
        return redirect(url_for('grades_page'))

    if request.method == 'POST':
        for code, _ in SUBJECTS:
            try:
                coeff = max(0.0, float(request.form.get(f'coeff_{code}', '1')))
            except (ValueError, TypeError):
                coeff = 1.0
            execute("""
                INSERT INTO class_subject_coefficients(school_id, class_id, subject_code, coefficient, school_year)
                VALUES(?,?,?,?,?)
                ON CONFLICT(class_id, subject_code, school_year)
                DO UPDATE SET coefficient=excluded.coefficient
            """, (sid(), class_id, code, coeff, syear()))
        flash(_('تم حفظ المعاملات بنجاح'), 'success')
        return redirect(url_for('class_coefficients', class_id=class_id))

    coeffs_rows = query(
        "SELECT subject_code, coefficient FROM class_subject_coefficients WHERE class_id=? AND school_year=?",
        (class_id, syear())
    )
    coeffs = {r['subject_code']: r['coefficient'] for r in coeffs_rows}

    return render_template('coefficients.html', cls=cls, subjects=SUBJECTS, coeffs=coeffs)


# ── تحليل نتائج القسم ─────────────────────────────────────────────
@app.route('/class/<int:class_id>/analytics')
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def class_analytics(class_id):
    cls = query('SELECT * FROM classes WHERE id=? AND school_id=?', (class_id, sid()), one=True)
    if not cls:
        flash(_('القسم غير موجود'), 'error')
        return redirect(url_for('grades_page'))

    yr       = syear()
    students = query('SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name', (class_id,))
    students_data = []

    for stu in students:
        # حاول حساب المعدل من نظام الفصول أولاً
        general_avg = calc_general_average(stu['id'], yr, class_id)

        tgs = query(
            "SELECT term, eval_type, grade FROM term_grades WHERE student_id=? AND school_year=?",
            (stu['id'], yr)
        )
        tests = [r['grade'] for r in tgs if r['eval_type'] in ('test1','test2') and r['grade'] is not None]
        exams = [r['grade'] for r in tgs if r['eval_type'] in ('exam1','exam2') and r['grade'] is not None]
        eval_avg = round(sum(tests)/len(tests), 2) if tests else None
        comp_avg = round(sum(exams)/len(exams), 2) if exams else None

        # إذا لم تكن بيانات الفصول موجودة، استخدم الدرجات العادية
        if general_avg is None:
            gs = query(
                "SELECT subject_code, grade FROM grades WHERE student_id=? AND school_year=? AND is_deleted=0",
                (stu['id'], yr)
            )
            general_avg = avg_grade(gs) if gs else None
            eval_avg    = general_avg
            comp_avg    = general_avg
            subject_grades = {g['subject_code']: g['grade'] for g in (gs or [])}
        else:
            subject_grades = {}
            for code, _ in SUBJECTS:
                ag = calc_subject_annual(stu['id'], code, yr)
                if ag is not None:
                    subject_grades[code] = ag

        if   general_avg is None: decision = None
        elif general_avg >= 10:   decision = 'PASSE'
        elif general_avg >= 8:    decision = 'PASSABLE'
        else:                     decision  = 'FAIBLE'

        students_data.append({
            'id':            stu['id'],
            'name':          stu['name'],
            'eval_avg':      eval_avg,
            'comp_avg':      comp_avg,
            'avg':           general_avg,
            'decision':      decision,
            'subject_grades': subject_grades,
        })

    students_data.sort(key=lambda x: x['avg'] or 0, reverse=True)
    for i, s in enumerate(students_data):
        s['rank'] = i + 1

    subjects_map = dict(SUBJECTS)
    return render_template('analytics.html',
        cls=cls, students_data=students_data,
        subjects=SUBJECTS, subjects_map=subjects_map,
        json_data=json.dumps(students_data, ensure_ascii=False))


# ── الحضور ─────────────────────────────────────────────────────────
@app.route('/attendance')
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def attendance_page():
    # المعلم يرى قسمه فقط
    if session.get('role') == 'teacher' and session.get('class_id'):
        classes = query('SELECT * FROM classes WHERE id=? AND school_id=? AND (is_deleted=0 OR is_deleted IS NULL)',
                        (session['class_id'], sid()))
    else:
        classes = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY level,name', (sid(),))
    class_id = request.args.get('class_id', '')
    sel_class     = None
    students_data = []
    if class_id:
        sel_class = query('SELECT * FROM classes WHERE id=? AND school_id=?',
                          (class_id, sid()), one=True)
        if sel_class:
            students = query(
                'SELECT * FROM students WHERE class_id=? AND is_active=1 ORDER BY name',
                (class_id,))
            for stu in students:
                att   = query('SELECT * FROM attendance WHERE student_id=? AND school_year=?',
                              (stu['id'], syear()))
                amap  = {a['month']: a['absent_days'] for a in att}
                total = sum(amap.values())
                students_data.append({'id': stu['id'], 'name': stu['name'],
                                      'map': amap, 'total': total})
    return render_template('attendance.html', classes=classes, sel_class=sel_class,
                           students_data=students_data, months=MONTHS, class_id=class_id)


@app.route('/attendance/save', methods=['POST'])
@school_required
@role_required('admin', 'teacher', 'staff', 'super_admin')
def save_attendance():
    data = request.get_json()
    sql  = """
        INSERT INTO attendance(student_id,month,absent_days,school_year)
        VALUES(?,?,?,?)
        ON CONFLICT(student_id,month,school_year)
        DO UPDATE SET absent_days=excluded.absent_days
    """
    rows = [(a['student_id'], a['month'], a['absent_days'], syear())
            for a in data.get('records', [])]
    execute_bulk(sql, rows)
    return jsonify({'ok': True})


# ── المستخدمون ─────────────────────────────────────────────────────
@app.route('/users')
@school_required
@admin_required
def users_list():
    users = query('SELECT * FROM users WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY role, name', (sid(),))
    # بناء خريطة أقسام كل معلم: {teacher_id: [class_name, ...]}
    tc_rows = query("""
        SELECT tc.teacher_id, c.name as class_name
        FROM teacher_classes tc
        JOIN classes c ON c.id = tc.class_id
        WHERE tc.school_id=?
    """, (sid(),))
    teacher_classes_map = {}
    for row in (tc_rows or []):
        teacher_classes_map.setdefault(row['teacher_id'], []).append(row['class_name'])
    return render_template('users.html', users=users, subjects=SUBJECTS,
                           teacher_classes_map=teacher_classes_map)


@app.route('/users/add', methods=['POST'])
@school_required
@admin_required
def add_user():
    f  = request.form
    pw = hash_pw(f.get('password') or os.urandom(16).hex())
    
    # توليد رمز التحقق
    verification_token = generate_verification_token()
    token_expires_at = (datetime.datetime.utcnow() + timedelta(hours=24)).isoformat()
    
    try:
        execute("""
            INSERT INTO users(school_id,name,email,password,role,subject_code,phone,
                            email_verified,verification_token,token_expires_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
        """, (sid(), f.get('name'), f.get('email'), pw,
              f.get('role', 'teacher'), f.get('subject_code'), f.get('phone'),
              0, verification_token, token_expires_at))
        
        # إرسال رسالة تحقق من البريد
        send_verification_email(f.get('email'), f.get('name'), verification_token)
        
        flash(f"تم إضافة المستخدم: {f.get('name')} ✉️ تم إرسال رابط التحقق إلى بريده الإلكتروني", 'success')
    except Exception as e:
        flash(_('البريد الإلكتروني مستخدم بالفعل'), 'error')
    return redirect(url_for('users_list'))


@app.route('/users/check-relations/<int:uid>')
@school_required
@admin_required
def users_check_relations(uid):
    timetable = query('SELECT COUNT(*) as c FROM timetable WHERE teacher_id=? AND school_id=? AND is_deleted=0', (uid, sid()), one=True)['c']
    tc        = query('SELECT COUNT(*) as c FROM teacher_classes WHERE teacher_id=? AND school_id=?', (uid, sid()), one=True)['c']
    relations = []
    if tc:        relations.append({'label': 'قسم مُعيَّن', 'count': tc})
    if timetable: relations.append({'label': 'حصة في الجدول', 'count': timetable})
    return jsonify({'has_relations': bool(relations), 'relations': relations})


@app.route('/users/delete/<int:uid>', methods=['POST'])
@school_required
@admin_required
def delete_user(uid):
    if uid == session['user_id']:
        flash(_('لا يمكنك حذف حسابك الخاص'), 'error')
        return redirect(url_for('users_list'))

    action = request.form.get('action', 'delete')
    try:
        if action == 'archive':
            execute('UPDATE users SET is_deleted=1 WHERE id=? AND school_id=?', (uid, sid()))
            flash(_('تمت أرشفة المستخدم'), 'success')
        else:
            execute('DELETE FROM teacher_classes WHERE teacher_id=? AND school_id=?', (uid, sid()))
            execute('UPDATE timetable SET is_deleted=1 WHERE teacher_id=? AND school_id=?', (uid, sid()))
            execute('DELETE FROM users WHERE id=? AND school_id=?', (uid, sid()))
            flash(_('تم حذف المستخدم'), 'success')
    except Exception:
        flash(_('تعذّر تنفيذ العملية على المستخدم'), 'error')
    return redirect(url_for('users_list'))


# ── الإحصائيات ─────────────────────────────────────────────────────
@app.route('/statistics')
@school_required
@role_required('admin', 'supervisor', 'staff', 'super_admin')
def statistics():
    classes  = query('SELECT * FROM classes WHERE school_id=? ORDER BY level,name', (sid(),))
    class_id = request.args.get('class_id', '')
    data      = None
    sel_class = None
    if class_id:
        sel_class = query('SELECT * FROM classes WHERE id=? AND school_id=?',
                          (class_id, sid()), one=True)
        if sel_class:
            students = query('SELECT * FROM students WHERE class_id=? AND is_active=1',
                             (class_id,))
            rows = []
            for stu in students:
                gs  = query('SELECT * FROM grades WHERE student_id=? AND school_year=?',
                            (stu['id'], syear()))
                att = query(
                    'SELECT SUM(absent_days) as tot FROM attendance WHERE student_id=? AND school_year=?',
                    (stu['id'], syear()), one=True)
                av  = avg_grade(gs)
                rows.append({
                    'id': stu['id'], 'name': stu['name'],
                    'grades': {g['subject_code']: g['grade'] for g in gs},
                    'avg': av, 'label': grade_label(av),
                    'pass': av is not None and av >= 10,
                    'absent': att['tot'] or 0,
                })
            rows.sort(key=lambda x: x['avg'] or 0, reverse=True)
            for i, r in enumerate(rows):
                r['rank'] = i + 1
            passing = [r for r in rows if r['pass']]
            subj_stats = []
            for code, sname in SUBJECTS:
                vals = [r['grades'].get(code) for r in rows
                        if r['grades'].get(code) is not None]
                if vals:
                    subj_stats.append({
                        'code': code, 'name': sname,
                        'avg':  round(sum(vals)/len(vals), 2),
                        'pass': sum(1 for v in vals if v >= 10),
                        'fail': sum(1 for v in vals if v < 10),
                        'total': len(vals),
                    })
            total = len(rows)
            data = {
                'students': rows,
                'passing': len(passing),
                'failing': total - len(passing),
                'total': total,
                'pass_rate': round(len(passing)/total*100) if total else 0,
                'class_avg': round(
                    sum(r['avg'] for r in rows if r['avg']) /
                    max(1, sum(1 for r in rows if r['avg'])), 2
                ) if rows else 0,
                'subjects': subj_stats,
            }
    return render_template('statistics.html', classes=classes, sel_class=sel_class,
                           data=data, subjects=SUBJECTS, class_id=class_id)

# ════════════════════════════════════════════════════════════════════
#  التقارير
# ════════════════════════════════════════════════════════════════════

@app.route('/reports')
@school_required
@role_required('admin', 'supervisor', 'staff', 'super_admin')
def reports():
    classes  = query('SELECT * FROM classes WHERE school_id=? AND (is_deleted=0 OR is_deleted IS NULL) ORDER BY name', (sid(),))
    students = query("""
        SELECT s.*, c.name as class_name
        FROM students s LEFT JOIN classes c ON c.id=s.class_id
        WHERE s.school_id=? AND s.is_active=1 ORDER BY s.name
    """, (sid(),))

    # إحصائيات سريعة — query واحد بدل N+1
    total_s = len(students)
    total_c = len(classes)

    passing = 0
    if total_s:
        avgs = query("""
            SELECT s.id, AVG(g.grade) as avg
            FROM students s
            JOIN grades g ON g.student_id = s.id
            WHERE s.school_id=? AND s.is_active=1 AND g.school_year=?
            GROUP BY s.id
        """, (sid(), syear()))
        avg_map = {r['id']: r['avg'] for r in avgs}
        passing = sum(1 for s in students if avg_map.get(s['id'], 0) and avg_map[s['id']] >= 10)

    pass_rate = round(passing / total_s * 100) if total_s else 0

    return render_template('reports.html',
        classes=classes, students=students,
        total_s=total_s, total_c=total_c, pass_rate=pass_rate)


# ════════════════════════════════════════════════════════════════════
#  الأرشيف — عرض العناصر المؤرشفة واستعادتها أو حذفها
# ════════════════════════════════════════════════════════════════════

@app.route('/archives/all')
@school_required
@admin_required
def archives_all():
    arc_classes  = query('SELECT * FROM classes  WHERE school_id=? AND is_deleted=1 ORDER BY name', (sid(),))
    arc_students = query('SELECT s.*, c.name as class_name FROM students s LEFT JOIN classes c ON c.id=s.class_id WHERE s.school_id=? AND s.is_active=0 ORDER BY s.name', (sid(),))
    arc_users    = query('SELECT * FROM users WHERE school_id=? AND is_deleted=1 ORDER BY name', (sid(),))
    arc_fees     = query('SELECT * FROM fees  WHERE school_id=? AND is_deleted=1 ORDER BY name', (sid(),))
    return render_template('archives_all.html',
        arc_classes=arc_classes, arc_students=arc_students,
        arc_users=arc_users, arc_fees=arc_fees)


@app.route('/archives/restore/<string:entity>/<int:eid>', methods=['POST'])
@school_required
@admin_required
def archives_restore(entity, eid):
    if entity == 'class':
        execute('UPDATE classes  SET is_deleted=0 WHERE id=? AND school_id=?', (eid, sid()))
        flash(_('تمت استعادة القسم'), 'success')
    elif entity == 'student':
        execute('UPDATE students SET is_active=1  WHERE id=? AND school_id=?', (eid, sid()))
        flash(_('تمت استعادة الطالب'), 'success')
    elif entity == 'user':
        execute('UPDATE users    SET is_deleted=0 WHERE id=? AND school_id=?', (eid, sid()))
        flash(_('تمت استعادة المستخدم'), 'success')
    elif entity == 'fee':
        execute('UPDATE fees     SET is_deleted=0 WHERE id=? AND school_id=?', (eid, sid()))
        flash(_('تمت استعادة الرسم'), 'success')
    return redirect(url_for('archives_all'))


@app.route('/archives/purge/<string:entity>/<int:eid>', methods=['POST'])
@school_required
@admin_required
def archives_purge(entity, eid):
    try:
        if entity == 'class':
            execute('DELETE FROM homework  WHERE class_id=? AND school_id=?', (eid, sid()))
            execute('UPDATE students SET class_id=NULL WHERE class_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM classes WHERE id=? AND school_id=?', (eid, sid()))
            flash(_('تم الحذف النهائي للقسم'), 'success')
        elif entity == 'student':
            # Verify student belongs to this school before deletion
            student = query('SELECT school_id FROM students WHERE id=?', (eid,), one=True)
            if not student or student['school_id'] != sid():
                flash(_('خطأ: الطالب غير موجود أو ينتمي لمدرسة أخرى'), 'error')
                return redirect(url_for('archives_all'))
            execute('DELETE FROM grades WHERE student_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM attendance WHERE student_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM payments WHERE student_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM students WHERE id=? AND school_id=?', (eid, sid()))
            flash(_('تم الحذف النهائي للطالب'), 'success')
        elif entity == 'user':
            execute('DELETE FROM teacher_classes WHERE teacher_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM users WHERE id=? AND school_id=?', (eid, sid()))
            flash(_('تم الحذف النهائي للمستخدم'), 'success')
        elif entity == 'fee':
            execute('UPDATE payments SET fee_id=NULL WHERE fee_id=? AND school_id=?', (eid, sid()))
            execute('DELETE FROM fees WHERE id=? AND school_id=?', (eid, sid()))
            flash(_('تم الحذف النهائي للرسم'), 'success')
    except Exception as e:
        flash(f'تعذّر الحذف: {e}', 'error')
    return redirect(url_for('archives_all'))


# ════════════════════════════════════════════════════════════════════
#  الإعدادات
# ════════════════════════════════════════════════════════════════════

@app.route('/settings', methods=['GET', 'POST'])
@school_required
@admin_required
def settings():
    school   = query('SELECT * FROM schools WHERE id=?', (sid(),), one=True)
    cfg      = query('SELECT * FROM school_settings WHERE school_id=?', (sid(),), one=True)

    if request.method == 'POST':
        f = request.form
        new_name = f.get('school_name', '').strip()
        new_year = f.get('school_year', '').strip()
        phone    = f.get('phone', '').strip()
        email    = f.get('email', '').strip()
        address  = f.get('address', '').strip()
        motto    = f.get('motto', '').strip()

        if new_name and new_name != school['name']:
            execute('UPDATE schools SET name=? WHERE id=?', (new_name, sid()))
            session['school_name'] = new_name

        if new_year:
            session['school_year'] = new_year

        # upsert school_settings
        year_to_save = new_year or (cfg['school_year'] if cfg else CURRENT_YEAR)
        if USE_PG:
            execute("""
                INSERT INTO school_settings (school_id, school_year, phone, email, address, motto)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (school_id) DO UPDATE
                SET school_year=EXCLUDED.school_year, phone=EXCLUDED.phone,
                    email=EXCLUDED.email, address=EXCLUDED.address, motto=EXCLUDED.motto
            """, (sid(), year_to_save, phone, email, address, motto))
        else:
            execute("""
                INSERT OR REPLACE INTO school_settings (school_id, school_year, phone, email, address, motto)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sid(), year_to_save, phone, email, address, motto))

        flash(_('✅ تم حفظ الإعدادات'), 'success')
        return redirect(url_for('settings'))

    gs = query('SELECT * FROM grade_settings WHERE school_id=?', (sid(),), one=True)
    levels_summary = query("""
        SELECT lc.level_code,
               COUNT(lc.subject_id) as count,
               SUM(lc.coefficient)  as total
        FROM level_coefficients lc
        WHERE lc.school_id=?
        GROUP BY lc.level_code
        ORDER BY lc.level_code
    """, (sid(),))
    return render_template('settings.html', school=school, cfg=cfg, gs=gs,
                           levels_summary=levels_summary)


@app.route('/settings/grades', methods=['POST'])
@school_required
@admin_required
def settings_grades():
    f = request.form
    tests  = int(f.get('tests_per_term', 2))
    ew     = float(f.get('eval_weight',  3))
    cw     = float(f.get('comp_weight',  1))
    tw1    = float(f.get('term1_weight', 1))
    tw2    = float(f.get('term2_weight', 2))
    tw3    = float(f.get('term3_weight', 3))
    if USE_PG:
        execute("""
            INSERT INTO grade_settings
              (school_id,tests_per_term,eval_weight,comp_weight,term1_weight,term2_weight,term3_weight)
            VALUES(?,?,?,?,?,?,?)
            ON CONFLICT(school_id) DO UPDATE SET
              tests_per_term=EXCLUDED.tests_per_term, eval_weight=EXCLUDED.eval_weight,
              comp_weight=EXCLUDED.comp_weight, term1_weight=EXCLUDED.term1_weight,
              term2_weight=EXCLUDED.term2_weight, term3_weight=EXCLUDED.term3_weight
        """, (sid(), tests, ew, cw, tw1, tw2, tw3))
    else:
        execute("""
            INSERT OR REPLACE INTO grade_settings
              (school_id,tests_per_term,eval_weight,comp_weight,term1_weight,term2_weight,term3_weight)
            VALUES(?,?,?,?,?,?,?)
        """, (sid(), tests, ew, cw, tw1, tw2, tw3))
    flash(_('✅ تم حفظ إعدادات الدرجات'), 'success')
    return redirect(url_for('settings'))


@app.route('/settings/subjects', methods=['GET'])
@school_required
@admin_required
def settings_subjects():
    from utils import init_default_subjects
    init_default_subjects(sid())
    levels = query("""
        SELECT lc.level_code, COUNT(*) as count, SUM(lc.coefficient) as total
        FROM level_coefficients lc WHERE lc.school_id=?
        GROUP BY lc.level_code ORDER BY lc.level_code
    """, (sid(),))
    all_subjects = query('SELECT * FROM subjects WHERE school_id=? ORDER BY name', (sid(),))
    return render_template('settings_subjects.html', levels=levels, all_subjects=all_subjects)


@app.route('/settings/subjects/<level_code>', methods=['GET', 'POST'])
@school_required
@admin_required
def settings_subjects_level(level_code):
    from utils import init_default_subjects
    init_default_subjects(sid())
    all_subjects = query('SELECT * FROM subjects WHERE school_id=? ORDER BY name', (sid(),))
    if request.method == 'POST':
        for subj in all_subjects:
            key   = f'coeff_{subj["id"]}'
            val   = request.form.get(key, '').strip()
            incl  = request.form.get(f'include_{subj["id"]}') == '1'
            if incl and val:
                coeff = float(val)
                if USE_PG:
                    execute("""
                        INSERT INTO level_coefficients(school_id,level_code,subject_id,coefficient)
                        VALUES(?,?,?,?)
                        ON CONFLICT(school_id,level_code,subject_id)
                        DO UPDATE SET coefficient=EXCLUDED.coefficient
                    """, (sid(), level_code, subj['id'], coeff))
                else:
                    execute("""
                        INSERT OR REPLACE INTO level_coefficients
                          (school_id,level_code,subject_id,coefficient)
                        VALUES(?,?,?,?)
                    """, (sid(), level_code, subj['id'], coeff))
            else:
                execute('DELETE FROM level_coefficients WHERE school_id=? AND level_code=? AND subject_id=?',
                        (sid(), level_code, subj['id']))
        flash(f'✅ تم حفظ معاملات المستوى {level_code}', 'success')
        return redirect(url_for('settings_subjects'))
    current = {r['subject_id']: r['coefficient'] for r in query(
        'SELECT subject_id, coefficient FROM level_coefficients WHERE school_id=? AND level_code=?',
        (sid(), level_code)
    )}
    return render_template('settings_subjects_level.html',
                           level_code=level_code, all_subjects=all_subjects, current=current)


# ════════════════════════════════════════════════════════════════════
#  تهيئة قاعدة البيانات عند بدء التطبيق (gunicorn + python مباشرة)
# ════════════════════════════════════════════════════════════════════
init_db()

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    print('\n' + '═'*60)
    print('  مدرستي — نظام إدارة المدارس متعدد المستأجرين')
    print(f'  🌐  http://localhost:{port}')
    print(f'  🔑  مشرف عام: {os.environ.get("SUPER_ADMIN_EMAIL", "(set SUPER_ADMIN_EMAIL env var)")}')
    print('═'*60 + '\n')
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', '0') == '1')
 
