"""
Test: pipeline/normalizer.py
Verifies date conversion and normalization logic.
"""
import sys
sys.path.insert(0, '.')

from pipeline.normalizer import normalize_date, normalize_article, normalize_all

errors = []

# --- Test normalize_date ---

def check_date(raw, expected):
    result = normalize_date(raw)
    if result != expected:
        errors.append(f"normalize_date('{raw}') = '{result}', expected '{expected}'")

# ISO full datetime
check_date("2026-07-14T14:47:19+05:45", "2026-07-14")
check_date("2026-08-25T10:08:00+00:00", "2026-08-25")

# ISO date only
check_date("2026-07-14", "2026-07-14")

# Year-month only
check_date("2026-08", "2026-08-01")

# Year only
check_date("2026", "2026-01-01")

# BS date strings
check_date("भदौ ९, २०८३", "2026-08-25")
check_date("साउन २८, २०८३", "2026-08-13")

# Empty
check_date("", "")
check_date(None, "")

# --- Test normalize_all ---
examples = normalize_all()

if len(examples) < 900:
    errors.append(f"normalize_all() returned {len(examples)} — expected 900+")

# Check required fields
for e in examples[:10]:
    if not e.example_id:
        errors.append(f"Missing example_id: {e.source_url}")
    if not e.claim_text:
        errors.append(f"Missing claim_text: {e.source_url}")
    if e.verdict_label not in [-1, 0, 1, 2]:
        errors.append(f"Invalid verdict_label {e.verdict_label}: {e.source_url}")
    if not e.source_name:
        errors.append(f"Missing source_name: {e.source_url}")

if errors:
    print("FAIL — normalizer errors:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(f"PASS — normalizer: {len(examples)} examples normalized correctly")
