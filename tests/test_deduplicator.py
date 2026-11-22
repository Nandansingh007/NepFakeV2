"""
Test: pipeline/deduplicator.py

NOTE (Phase 0): ported 1:1. The real data has 0 duplicates, so these checks
never exercise the dedup logic itself (which copy is kept, URL variants).
That is Phase 1 work.
"""
import pytest

pytestmark = pytest.mark.data


def test_dedup_does_not_increase_count(normalized, deduped):
    assert len(deduped) <= len(normalized)


def test_dedup_removal_rate_reasonable(normalized, deduped):
    removal_rate = (len(normalized) - len(deduped)) / len(normalized)
    assert removal_rate <= 0.05, f"dedup removed {removal_rate:.1%}"


def test_no_duplicate_urls_after_dedup(deduped):
    seen, dupes = set(), []
    for e in deduped:
        key = (e.source_name, e.source_url)
        if key in seen:
            dupes.append(e.source_url)
        seen.add(key)
    assert not dupes, dupes[:10]
