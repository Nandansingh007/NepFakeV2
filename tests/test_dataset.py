"""
Test: data/nepfakev2.csv and data/stats.json
Verifies the final research dataset is correct.
"""
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, '.')

errors = []
warnings = []

# --- Test nepfakev2.csv ---
csv_path = Path("data/nepfakev2.csv")
if not csv_path.exists():
    print("FAIL — data/nepfakev2.csv not found")
    sys.exit(1)

df = pd.read_csv(csv_path)

# Row count
if len(df) < 900:
    errors.append(f"Only {len(df)} rows — expected 900+")

# Required columns
required_cols = [
    'example_id', 'claim_text', 'verdict_label', 'verdict_label_text',
    'evidence_text', 'source_name', 'source_url', 'date_published',
    'is_native_nepali', 'topic_category', 'label_basis', 'annotator_notes'
]
for col in required_cols:
    if col not in df.columns:
        errors.append(f"Missing column: {col}")

# No nulls in critical columns
critical_cols = ['example_id', 'claim_text', 'verdict_label', 'source_name', 'source_url']
for col in critical_cols:
    if col in df.columns:
        nulls = df[col].isnull().sum()
        if nulls > 0:
            errors.append(f"{col} has {nulls} null values")

# Unique example_ids
if 'example_id' in df.columns:
    dupes = df['example_id'].duplicated().sum()
    if dupes > 0:
        errors.append(f"{dupes} duplicate example_ids")

# Valid verdict labels — CSV must NOT contain -1 (filtered by exporter)
if 'verdict_label' in df.columns:
    valid = {0, 1, 2}
    invalid = df[~df['verdict_label'].isin(valid)]
    if len(invalid) > 0:
        errors.append(
            f"{len(invalid)} invalid verdict labels in CSV "
            f"(including -1 UNKNOWN — should have been filtered by exporter)"
        )

# Nepali script coverage
if 'is_native_nepali' in df.columns:
    nepali_pct = df['is_native_nepali'].mean() * 100
    if nepali_pct < 90:
        warnings.append(f"Only {nepali_pct:.1f}% Nepali script — expected 90%+")

# Source distribution — only active sources
if 'source_name' in df.columns:
    sources = df['source_name'].value_counts()
    expected_sources = ['techpana', 'nepalfactcheck']
    for s in expected_sources:
        if s not in sources:
            errors.append(f"Source missing from dataset: {s}")
    # No dead sources
    dead_sources = ['nepalcheck', 'bbc_nepali', 'kantipur']
    for s in dead_sources:
        if s in sources.index:
            errors.append(f"Dead source found in dataset: {s}")

# No empty evidence text
if 'evidence_text' in df.columns:
    empty = df['evidence_text'].isna().sum()
    if empty > 0:
        errors.append(f"{empty} empty evidence texts")

# Date format check
if 'date_published' in df.columns:
    invalid_dates = 0
    for d in df['date_published'].dropna():
        if len(str(d)) < 10:
            invalid_dates += 1
    if invalid_dates > 10:
        warnings.append(f"{invalid_dates} records with short date strings")

# --- Test stats.json ---
stats_path = Path("data/stats.json")
if not stats_path.exists():
    errors.append("data/stats.json not found")
else:
    with open(stats_path, "r", encoding="utf-8") as f:
        stats = json.load(f)

    # total_examples matches exported CSV (not including unknowns)
    if stats.get('total_examples') != len(df):
        errors.append(
            f"stats.json total_examples ({stats.get('total_examples')}) != CSV ({len(df)})"
        )

    # total_including_unknown >= total_examples
    # (only present after pipeline runs with updated exporter.py)
    if 'total_including_unknown' in stats:
        if stats['total_including_unknown'] < stats.get('total_examples', 0):
            errors.append(
                f"total_including_unknown ({stats['total_including_unknown']}) "
                f"< total_examples ({stats.get('total_examples')}) — impossible"
            )

    # Last updated is recent
    last_updated = stats.get('last_updated', '')
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            hours_ago = (now - dt).total_seconds() / 3600
            if hours_ago > 48:
                warnings.append(f"stats.json updated {hours_ago:.0f} hours ago")
        except Exception:
            pass

    # Required keys
    required_keys = [
        'total_examples', 'label_distribution',
        'source_distribution', 'topic_distribution', 'date_range',
        'language', 'quality'
    ]
    for key in required_keys:
        if key not in stats:
            errors.append(f"stats.json missing key: {key}")

# --- Test nepfakev2.json ---
json_path = Path("data/nepfakev2.json")
if not json_path.exists():
    errors.append("data/nepfakev2.json not found")
else:
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    if len(json_data) != len(df):
        errors.append(
            f"JSON count ({len(json_data)}) != CSV count ({len(df)})"
        )

if errors:
    print("FAIL — dataset errors:")
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
    sources = df['source_name'].value_counts().to_dict() if 'source_name' in df.columns else {}
    print(f"PASS — dataset: {len(df)} rows, sources: {sources}")