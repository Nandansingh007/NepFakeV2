"""
Test: full pipeline end to end
Verifies normalize → deduplicate → export produces correct output.
"""
import sys
import json
sys.path.insert(0, '.')

errors = []

from pipeline.normalizer import normalize_all
from pipeline.deduplicator import deduplicate, get_dedup_stats
from pipeline.exporter import export, compute_stats

# Run pipeline
examples = normalize_all()
deduped = deduplicate(examples)
stats = compute_stats(deduped)

# Check total
if len(deduped) < 900:
    errors.append(f"Pipeline produced {len(deduped)} examples — expected 900+")

# Check stats structure
required_keys = [
    'total_examples', 'total_including_unknown', 'label_distribution',
    'source_distribution', 'topic_distribution', 'date_range',
    'language', 'quality'
]
for key in required_keys:
    if key not in stats:
        errors.append(f"compute_stats() missing key: {key}")

# total_examples (exported) <= total_including_unknown (full)
if stats.get('total_examples', 0) > stats.get('total_including_unknown', 0):
    errors.append(
        f"total_examples ({stats.get('total_examples')}) > "
        f"total_including_unknown ({stats.get('total_including_unknown')}) — impossible"
    )

# Check label distribution totals against total_including_unknown
if 'label_distribution' in stats:
    label_total = sum(
        v['count'] for v in stats['label_distribution'].values()
    )
    if label_total != stats.get('total_including_unknown', label_total):
        errors.append(
            f"Label distribution total ({label_total}) != "
            f"total_including_unknown ({stats.get('total_including_unknown')})"
        )

# Check source distribution
if 'source_distribution' in stats:
    source_total = sum(
        v['count'] for v in stats['source_distribution'].values()
    )
    if source_total != len(deduped):
        errors.append(
            f"Source distribution total ({source_total}) != examples ({len(deduped)})"
        )

# Check date range makes sense
if 'date_range' in stats:
    oldest = stats['date_range'].get('oldest', '')
    newest = stats['date_range'].get('newest', '')
    if oldest and newest:
        if oldest > newest:
            errors.append(f"Date range invalid: oldest {oldest} > newest {newest}")
        if oldest < '2020-01-01':
            errors.append(f"Oldest date {oldest} is before 2020")
        if newest > '2030-01-01':
            errors.append(f"Newest date {newest} is after 2030")

# Check language stats
if 'language' in stats:
    nepali_pct = stats['language'].get('nepali_pct', '0%')
    pct_val = float(nepali_pct.replace('%', ''))
    if pct_val < 90:
        errors.append(f"Only {nepali_pct} Nepali script — expected 90%+")

if errors:
    print("FAIL — pipeline errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print(
        f"PASS — pipeline: {len(deduped)} examples, "
        f"labels: {stats['label_distribution']}"
    )