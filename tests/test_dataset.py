"""
Test: the committed data/nepfakev2.csv, data/nepfakev2.json, data/stats.json.

This checks the committed *files*. That the files are what the code makes
from raw/ is checked in tests/test_rebuild_reproducible.py (test plan N10).
"""
import json
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.data

# Schema 2.0: exactly these columns, in this order (schema/schema.py COLUMNS)
REQUIRED_COLS = [
    "example_id", "claim_text", "claim_source", "headline",
    "verdict_label", "verdict_label_text", "label_fine", "label_source",
    "in_main_benchmark", "evidence_text", "conclusion_text",
    "external_evidence_urls", "source_name", "source_type", "source_url",
    "date_published", "date_precision", "date_scraped", "language",
    "is_native_nepali", "label_basis", "topic_category", "annotator_notes",
    "claim_group_id", "split", "split_random", "schema_version",
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
    assert list(df.columns) == REQUIRED_COLS


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


def test_label_source_values(df):
    from config.settings import LABEL_SOURCES
    bad = df[~df['label_source'].isin(set(LABEL_SOURCES))]
    assert bad.empty, f"{len(bad)} rows with unknown label_source: {bad['label_source'].unique()[:5]}"


def test_schema_version_matches_code(df, stats):
    # Fails if data/ was not regenerated after a schema bump
    from config.settings import SCHEMA_VERSION
    assert set(df['schema_version'].astype(str)) == {SCHEMA_VERSION}
    assert stats.get('schema_version') == SCHEMA_VERSION


def test_label_fine_values(df):
    from config.settings import LABELS_FINE, LABEL_FINE_TO_COARSE
    bad = df[~df['label_fine'].isin(set(LABELS_FINE))]
    assert bad.empty, f"{len(bad)} rows with unknown label_fine"
    mismatch = df[df['label_fine'].map(LABEL_FINE_TO_COARSE) != df['verdict_label']]
    assert mismatch.empty, f"{len(mismatch)} rows where label_fine and verdict_label disagree"


def test_stats_main_benchmark_matches_csv(df, stats):
    assert stats['main_benchmark']['total'] == int(df['in_main_benchmark'].sum())


def test_json_count_matches_csv(df):
    path = Path("data/nepfakev2.json")
    assert path.exists(), "data/nepfakev2.json not found"
    assert len(json.loads(path.read_text(encoding="utf-8"))) == len(df)
