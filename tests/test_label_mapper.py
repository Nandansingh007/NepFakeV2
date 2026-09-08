"""
Test: pipeline/label_mapper.py
Verifies all verdict strings map to correct labels.
"""
import sys
sys.path.insert(0, '.')

from pipeline.label_mapper import map_verdict, is_mappable

errors = []

def check(verdict, expected_label):
    label, name = map_verdict(verdict)
    if label != expected_label:
        errors.append(
            f"map_verdict('{verdict}') = {label} ({name}), expected {expected_label}"
        )

# Label 1 — FALSE/MISLEADING
check("मिथ्या",         1)
check("मिथ्या सूचना",   1)
check("भ्रामक",         1)
check("भ्रामक सूचना",   1)
check("झुटो",           1)
check("गलत",            1)
check("असत्य",          1)
check("भ्रम",           1)

# Label 0 — REAL
check("सही",            0)
check("सही सूचना",      0)
check("साँचो",          0)
check("सत्य",           0)

# Label 2 — UNVERIFIED
check("अपुष्ट",         2)
check("अपुष्ट सूचना",   2)

# Label -1 — UNKNOWN
check("",               -1)
check("   ",            -1)

# is_mappable
assert is_mappable("भ्रामक") == True
assert is_mappable("") == False
assert is_mappable("unknown garbage") == False

if errors:
    print("FAIL — label_mapper errors:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("PASS — label_mapper: all verdicts mapped correctly")
