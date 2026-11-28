"""
Test: pipeline/deduplicator.py (on the real data). Which snapshot is kept,
and the quality guard, are tested in tests/test_identity_and_snapshots.py.
"""
import pytest

pytestmark = pytest.mark.data


def test_dedup_does_not_increase_count(normalized, deduped):
    assert len(deduped) <= len(normalized)


def test_dedup_keeps_one_row_per_article(normalized, deduped):
    # Replaces the Phase 0 check "dedup removes at most 5%". Since 2.0 every
    # re-scrape adds a second snapshot of each article, so a full re-scrape
    # makes dedup remove about half the rows, and that is correct. What must
    # hold is: exactly one row per article (source + canonical URL), and no
    # article lost.
    from utils.helpers import canonical_url
    articles = {(e.source_name, canonical_url(e.source_url)) for e in normalized}
    assert len(deduped) == len(articles), (len(deduped), len(articles))


def test_no_duplicate_urls_after_dedup(deduped):
    seen, dupes = set(), []
    for e in deduped:
        key = (e.source_name, e.source_url)
        if key in seen:
            dupes.append(e.source_url)
        seen.add(key)
    assert not dupes, dupes[:10]
