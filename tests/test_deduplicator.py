"""
Test: pipeline/deduplicator.py
Verifies URL deduplication works correctly.
"""
import sys
sys.path.insert(0, '.')

from pipeline.normalizer import normalize_all
from pipeline.deduplicator import deduplicate, get_dedup_stats

errors = []

examples = normalize_all()
deduped = deduplicate(examples)
stats = get_dedup_stats(examples, deduped)

# Should not increase count
if len(deduped) > len(examples):
    errors.append(f"Dedup increased count: {len(examples)} -> {len(deduped)}")

# Should not drop too many (>5%)
removal_rate = (len(examples) - len(deduped)) / len(examples)
if removal_rate > 0.05:
    errors.append(
        f"Dedup removed {removal_rate*100:.1f}% of records — seems too high"
    )

# Check no duplicate source URLs within same source
seen = {}
for e in deduped:
    key = (e.source_name, e.source_url)
    if key in seen:
        errors.append(f"Duplicate found after dedup: {e.source_url}")
    seen[key] = True

if errors:
    print("FAIL — deduplicator errors:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print(
        f"PASS — deduplicator: {stats['removed']} duplicates removed, "
        f"{stats['after']} records kept"
    )
