"""
Test: normalize -> deduplicate -> compute_stats end to end (in memory;
nothing is written to data/).
"""
import pytest

from pipeline.exporter import compute_stats

pytestmark = pytest.mark.data


@pytest.fixture(scope="module")
def stats(deduped):
    from pipeline.normalizer import LAST_EXCLUSIONS
    return compute_stats(deduped, LAST_EXCLUSIONS)


def test_pipeline_count(deduped):
    assert len(deduped) >= 900


def test_stats_keys(stats):
    required = [
        'total_examples', 'total_including_unknown', 'label_distribution',
        'source_distribution', 'topic_distribution', 'date_range',
        'language', 'quality',
    ]
    missing = [k for k in required if k not in stats]
    assert not missing, missing


def test_total_including_unknown_counts_exclusions(stats):
    # 2.0: total_including_unknown = exported rows + rows left out (excluded.csv).
    # Before 2.0 both numbers were always equal, which hid the 23 exclusions.
    assert stats['total_including_unknown'] == (
        stats['total_examples'] + sum(stats['excluded'].values()))
    assert stats['total_including_unknown'] > stats['total_examples']


def test_label_distribution_sums_to_total(stats):
    label_total = sum(v['count'] for v in stats['label_distribution'].values())
    assert label_total == stats['total_examples']


def test_source_distribution_sums_to_examples(stats, deduped):
    source_total = sum(v['count'] for v in stats['source_distribution'].values())
    assert source_total == len(deduped)


def test_date_range_sane(stats):
    oldest = stats['date_range'].get('oldest', '')
    newest = stats['date_range'].get('newest', '')
    assert oldest and newest
    assert oldest <= newest
    assert oldest >= '2020-01-01'
    assert newest <= '2030-01-01'


def test_mostly_nepali(stats):
    pct = float(stats['language'].get('nepali_pct', '0%').replace('%', ''))
    assert pct >= 90, f"only {pct}% Nepali script"
