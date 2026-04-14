import re

path = r'c:/Users/Lenovo/Masaüstü/uygulama/مدرستي/templates/login.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update <head> to inject base.css, keep font links
head_css = """<link rel="stylesheet" href="/static/css/base.css">
<script>
  (function() {
    const savedTheme = localStorage.getItem('mdrasati-theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
      document.documentElement.setAttribute('data-theme', 'dark');
    }
  })();
</script>
<style>
"""

# We find where `<style>` starts and replace the root and font things.
content = content.replace('<style>', head_css)


# Insert Theme toggle inside .form-logo
logo_replace = """<div class="form-logo">
      <div class="form-logo-icon">🏫</div>
      <div class="form-logo-text">
        <div class="name">مدرستي</div>
        <div class="tagline">{{ _('نظام إدارة المدارس') }}</div>
      </div>
      <button type="button" class="theme-toggle" id="themeToggle" aria-label="Toggle Theme" style="margin-inline-start: auto; border-radius: 8px; width: 34px; height: 34px; border: 1.5px solid var(--border); background: var(--card-bg); cursor: pointer; color: var(--text);">🌙</button>
    </div>"""
content = re.sub(r'<div class="form-logo">.*?</div>\s+</div>', logo_replace, content, flags=re.DOTALL)


# Update hardcoded colors to CSS variables from base.css
content = content.replace('background: #fff;', 'background: var(--card-bg);')
content = content.replace('background: #FAFBFF;', 'background: var(--input-bg);')
content = content.replace('color: #fff;', 'color: var(--white);')
content = content.replace('color: var(--text);', 'color: var(--text);')
content = content.replace('background: #F8FAFC;', 'background: var(--input-bg);')
content = content.replace('background: #FEF2F2;', 'background: var(--badge-red-bg);')
content = content.replace('color: #991B1B;', 'color: var(--badge-red-cl);')


# Append JS at the end of body
script_addition = """
<script>
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    themeToggle.textContent = isDark ? '☀️' : '🌙';
    
    themeToggle.addEventListener('click', () => {
      const currentDark = document.documentElement.getAttribute('data-theme') === 'dark';
      if (currentDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('mdrasati-theme', 'light');
        themeToggle.textContent = '🌙';
      } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('mdrasati-theme', 'dark');
        themeToggle.textContent = '☀️';
      }
    });

    // Ripple & loading effect for btn-login
    const btn = document.querySelector('.btn-login');
    if (btn) {
      btn.addEventListener('click', function(e) {
        if(this.closest('form').checkValidity()) {
          this.classList.add('loading');
          this.innerHTML = '<span class="spinner" style="display:inline-block;width:14px;height:14px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite;margin-inline-end:8px;"></span> ' + this.innerText;
        }
      });
    }
  }
</script>
<style>@keyframes spin { 100% { transform: rotate(360deg); } }</style>
</body>
"""
content = content.replace('</body>', script_addition)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("login.html updated successfully!")
