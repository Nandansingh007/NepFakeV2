"""
Test: the committed data/nepfakev2.csv, data/nepfakev2.json, data/stats.json.

NOTE (Phase 0): ported 1:1. This checks the committed *files*, not the
code. A stale file still passes. A "rebuild from raw/ reproduces the CSV
byte-for-byte" check is planned for later (test plan N10).
"""
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.data

REQUIRED_COLS = [
    'example_id', 'claim_text', 'verdict_label', 'verdict_label_text',
    'evidence_text', 'source_name', 'source_url', 'date_published',
    'is_native_nepali', 'topic_category', 'label_basis', 'annotator_notes',
]


@pytest.fixture(scope="module")
def df():
    path = Path("data/nepfakev2.csv")
    assert path.exists(), "data/nepfakev2.csv not found"
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def stats():
    path = Path("data/stats.json")
    assert path.exists(), "data/stats.json not found"
    return json.loads(path.read_text(encoding="utf-8"))


def test_row_count(df):
    assert len(df) >= 900


def test_required_columns(df):
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    assert not missing, missing


@pytest.mark.parametrize(
    "col", ['example_id', 'claim_text', 'verdict_label', 'source_name', 'source_url']
)
def test_no_nulls_in_critical_columns(df, col):
    assert df[col].isnull().sum() == 0


def test_unique_example_ids(df):
    assert df['example_id'].duplicated().sum() == 0


def test_only_exportable_labels(df):
    # CSV must not contain -1 (UNKNOWN); the exporter filters it
    bad = df[~df['verdict_label'].isin({0, 1, 2})]
    assert bad.empty, f"{len(bad)} rows with invalid labels"


def test_nepali_share(df):
    pct = df['is_native_nepali'].mean() * 100
    if pct < 90:
        warnings.warn(f"only {pct:.1f}% Nepali script")


def test_sources(df):
    sources = set(df['source_name'].unique())
    assert {'techpana', 'nepalfactcheck'} <= sources
    assert not sources & {'nepalcheck', 'bbc_nepali', 'kantipur'}, "dead source present"


def test_no_empty_evidence(df):
    assert df['evidence_text'].isna().sum() == 0


def test_date_format(df):
    short = sum(1 for d in df['date_published'].dropna() if len(str(d)) < 10)
    if short > 10:
        warnings.warn(f"{short} records with short date strings")


def test_stats_total_matches_csv(df, stats):
    assert stats.get('total_examples') == len(df)


def test_stats_total_including_unknown(stats):
    if 'total_including_unknown' in stats:
        assert stats['total_including_unknown'] >= stats.get('total_examples', 0)


def test_stats_keys(stats):
    required = [
        'total_examples', 'label_distribution', 'source_distribution',
        'topic_distribution', 'date_range', 'language', 'quality',
    ]
    missing = [k for k in required if k not in stats]
    assert not missing, missing


def test_stats_freshness(stats):
    last_updated = stats.get('last_updated', '')
    if not last_updated:
        return
    dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    if hours > 48:
        warnings.warn(f"stats.json updated {hours:.0f} hours ago")


def test_json_count_matches_csv(df):
    path = Path("data/nepfakev2.json")
    assert path.exists(), "data/nepfakev2.json not found"
    assert len(json.loads(path.read_text(encoding="utf-8"))) == len(df)
