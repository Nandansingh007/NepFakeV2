"""
Test: security checks
Verifies no secrets are hardcoded in code files.
"""
import sys
import subprocess
from pathlib import Path
sys.path.insert(0, '.')

errors = []
warnings = []

# --- Check .gitignore ---
gitignore_path = Path(".gitignore")
if not gitignore_path.exists():
    errors.append(".gitignore not found")
else:
    content = gitignore_path.read_text()
    required_ignores = ['.env', 'venv/', 'logs/']
    for item in required_ignores:
        if item not in content:
            warnings.append(f".gitignore missing: {item}")

# --- Check no secrets hardcoded in source files ---
# Exclude test files themselves from this check
SECRET_PATTERNS = [
    'tskey-auth',
    'REDACTED',
    'REDACTED',
]

# Only check source files — not test files
source_dirs = ['scrapers', 'pipeline', 'config', 'schema', 'utils', '.github']
py_files = []
for d in source_dirs:
    py_files.extend(Path(d).rglob('*.py') if Path(d).exists() else [])
yml_files = list(Path('.github').rglob('*.yml')) if Path('.github').exists() else []

for pattern in SECRET_PATTERNS:
    for f in py_files + yml_files:
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            if pattern in content:
                errors.append(f"Secret pattern found in {f}")
        except Exception:
            pass

# --- Check no .env file committed ---
env_path = Path(".env")
if env_path.exists():
    result = subprocess.run(
        ['git', 'ls-files', '.env'],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        errors.append(".env file is tracked by git")

# --- Check no secrets in git history ---
secret_searches = [
    'tskey-auth',
    'REDACTED',
    'REDACTED',
]

for secret in secret_searches:
    result = subprocess.run(
        ['git', 'log', '--all', f'-S{secret}', '--oneline'],
        capture_output=True, text=True
    )
    if result.stdout.strip():
        errors.append(f"Secret '{secret}' found in git history")

# --- Check requirements.txt ---
req_path = Path("requirements.txt")
if req_path.exists():
    content = req_path.read_text()
    test_packages = ['playwright', 'playwright-stealth', 'curl_cffi']
    for pkg in test_packages:
        if pkg in content:
            warnings.append(f"Unused test package in requirements.txt: {pkg}")

# --- Check .gitignore has raw/ NOT ignored ---
if gitignore_path.exists():
    content = gitignore_path.read_text()
    if 'raw/' in content:
        errors.append(".gitignore contains raw/ — raw data will not be committed")

if errors:
    print("FAIL - security errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    sys.exit(1)
else:
    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    print("PASS - security: no secrets found in source code or git history")