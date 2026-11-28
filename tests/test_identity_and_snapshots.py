"""
Test: stable IDs, newest-snapshot dedup, same-day save, full re-scrape mode,
and the record of excluded articles (v2.0, commit 2).

Brief items: S1 (IDs), S2 (re-scrape needs "newest wins"), test plan N5-N7.
"""
import json
import os
from pathlib import Path

import pytest

from schema.schema import NepFakeV2Example


# -----------------------------------------------------------------------------
# canonical_url and stable IDs (S1)
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("a, b", [
    ("https://techpana.com/2026/159019/slug", "https://techpana.com/2026/159019/slug?tab=nepali"),
    ("https://techpana.com/2026/159019/slug", "https://techpana.com/2026/159019/slug/"),
    ("https://nepalfactcheck.org/2026/09/x/", "https://www.nepalfactcheck.org/2026/09/x"),
    ("https://nepalfactcheck.org/2026/09/x/", "http://NepalFactCheck.org/2026/09/x/#top"),
])
def test_canonical_url_variants(a, b):
    from utils.helpers import canonical_url
    assert canonical_url(a) == canonical_url(b)


def test_example_id_techpana_uses_article_number():
    from schema.schema import make_example_id
    assert make_example_id("techpana", "https://techpana.com/2026/159019/slug?x=1") == "NF2_tp_159019"


def test_example_id_nfc_is_url_hash_and_stable():
    from schema.schema import make_example_id
    a = make_example_id("nepalfactcheck", "https://nepalfactcheck.org/2026/09/x/")
    b = make_example_id("nepalfactcheck", "https://www.nepalfactcheck.org/2026/09/x")
    assert a == b
    assert a.startswith("NF2_nfc_") and len(a) == len("NF2_nfc_") + 10


def test_example_id_does_not_depend_on_date_or_order():
    from schema.schema import make_example_id
    import inspect
    params = list(inspect.signature(make_example_id).parameters)
    assert params == ["source_name", "source_url"]


@pytest.mark.data
def test_ids_unique_and_new_format(deduped):
    # after dedup: two snapshots of one URL share an ID until dedup keeps one
    ids = [e.example_id for e in deduped]
    assert len(ids) == len(set(ids))
    assert all(i.startswith(("NF2_tp_", "NF2_nfc_")) for i in ids)


@pytest.mark.data
def test_ids_unchanged_when_an_older_raw_file_is_added(tmp_path, monkeypatch, normalized):
    # Copy raw/ and add an extra TechPana file that sorts FIRST. Under the old
    # running-number scheme this renumbered every NFC row.
    import shutil
    from config import settings
    from pipeline import normalizer
    raw = tmp_path / "raw"
    shutil.copytree("raw", raw)
    src = json.loads(Path("raw/techpana/2026-11-02.json").read_text(encoding="utf-8"))[0]
    extra = dict(src, source_url="https://techpana.com/2020/000001/extra-test-article")
    (raw / "techpana" / "2000-01-01.json").write_text(
        json.dumps([extra], ensure_ascii=False), encoding="utf-8")
    dirs = {"techpana": raw / "techpana", "nepalfactcheck": raw / "nepalfactcheck"}
    monkeypatch.setattr(normalizer, "RAW_DIRS", dirs)
    again = {e.source_url: e.example_id for e in normalizer.normalize_all()}
    before = {e.source_url: e.example_id for e in normalized}
    changed = [u for u in before if again.get(u) != before[u]]
    assert not changed, changed[:5]


# -----------------------------------------------------------------------------
# Dedup keeps the NEWEST snapshot (S2 / N7)
# -----------------------------------------------------------------------------

def _ex(url, scraped, label_text="FALSE_MISLEADING", label=1, fine="FALSE"):
    return NepFakeV2Example(
        example_id="x", claim_text="c", verdict_label=label,
        verdict_label_text=label_text, evidence_text="e" * 60,
        source_name="techpana", source_url=url, date_scraped=scraped,
        label_fine=fine)


def test_dedup_keeps_newest_snapshot():
    from pipeline.deduplicator import deduplicate
    old = _ex("https://techpana.com/2026/1/a", "2026-09-12", fine="FALSE")
    new = _ex("https://techpana.com/2026/1/a/?tab=nepali", "2026-12-14", fine="MISLEADING")
    kept = deduplicate([old, new])
    assert len(kept) == 1 and kept[0].date_scraped == "2026-12-14"
    kept = deduplicate([new, old])          # order of input must not matter
    assert len(kept) == 1 and kept[0].date_scraped == "2026-12-14"


def test_dedup_reports_label_changes():
    from pipeline import deduplicator
    old = _ex("https://techpana.com/2026/1/a", "2026-09-12", fine="FALSE")
    new = _ex("https://techpana.com/2026/1/a", "2026-12-14", fine="MISLEADING")
    other = _ex("https://techpana.com/2026/2/b", "2026-09-12")
    deduplicator.deduplicate([old, new, other])
    report = deduplicator.LAST_REPORT
    assert report["replaced"] == 1
    assert report["label_changed"] == [
        {"source_url": "https://techpana.com/2026/1/a", "old": "FALSE", "new": "MISLEADING",
         "old_scraped": "2026-09-12", "new_scraped": "2026-12-14"}]


@pytest.mark.data
def test_rescrape_does_not_flip_many_labels(normalized):
    # Gate for the Phase 2 re-scrape: when a newer snapshot replaces an older
    # one, at most 10% of the replaced rows (and at least 2 are always
    # allowed, for a real correction by a fact-checker) may change
    # label_fine. More means the scraper broke, not that the fact-checkers
    # changed their minds. (Vacuous until a URL is scraped twice.)
    from pipeline import deduplicator
    deduplicator.deduplicate(normalized)
    r = deduplicator.LAST_REPORT
    if r["replaced"] == 0:
        pytest.skip("no URL has two snapshots yet")
    assert len(r["label_changed"]) <= max(2, 0.10 * r["replaced"]), r["label_changed"][:10]


# -----------------------------------------------------------------------------
# save_raw: a fresh scrape on the same day replaces the earlier record
# -----------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_save_raw_same_day_newest_wins(tmp_path, monkeypatch):
    from scrapers.nepalfactcheck import NepalfactcheckScraper
    from schema.schema import RawArticle
    s = NepalfactcheckScraper()
    monkeypatch.setattr(s, "raw_dir", tmp_path)
    def art(verdict):
        return RawArticle(source_name="nepalfactcheck", source_url="https://nepalfactcheck.org/2026/01/a/",
                          title="t", body_text="b", raw_verdict_text=verdict,
                          date_published="2026-01-01", date_scraped="2026-12-14")
    s.save_raw([art("मिथ्या सूचना")])
    path = s.save_raw([art("भ्रामक सूचना")])
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["raw_verdict_text"] == "भ्रामक सूचना"


# -----------------------------------------------------------------------------
# Full re-scrape mode (Phase 2)
# -----------------------------------------------------------------------------

@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_full_rescrape_ignores_cutoff(monkeypatch):
    from scrapers.nepalfactcheck import NepalfactcheckScraper
    monkeypatch.delenv("NEPFAKE_FULL_RESCRAPE", raising=False)
    normal = NepalfactcheckScraper()
    monkeypatch.setenv("NEPFAKE_FULL_RESCRAPE", "1")
    full = NepalfactcheckScraper()
    assert full.last_published_date is None
    assert full.is_before_cutoff("2020-01-01") is False
    if normal.last_published_date:
        assert normal.is_before_cutoff("2020-01-01") is True


def test_collector_has_full_flag():
    from pipeline.collector import parse_args
    assert parse_args(["--full"]).full is True
    assert parse_args([]).full is False


def test_last_published_date_never_goes_back():
    from pipeline.collector import next_last_published
    assert next_last_published("2026-11-06", "2026-10-01") == "2026-11-06"
    assert next_last_published("2026-11-06", "2026-11-20") == "2026-11-20"
    assert next_last_published(None, "2026-11-20") == "2026-11-20"
    assert next_last_published("2026-11-06", None) == "2026-11-06"


def test_weekly_workflow_offers_full_rescrape():
    text = Path(".github/workflows/weekly_scrape.yml").read_text(encoding="utf-8")
    assert "full_rescrape" in text
    assert "NEPFAKE_FULL_RESCRAPE" in text


# -----------------------------------------------------------------------------
# Excluded articles are recorded, not silently dropped (N5)
# -----------------------------------------------------------------------------

@pytest.mark.data
def test_exclusions_are_recorded(normalized):
    from pipeline.normalizer import LAST_EXCLUSIONS
    reasons = {}
    for x in LAST_EXCLUSIONS:
        reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
    assert reasons.get("explainer", 0) >= 19
    assert reasons.get("not_a_factcheck", 0) >= 4
    for x in LAST_EXCLUSIONS:
        assert set(x) >= {"source_name", "source_url", "reason"}


@pytest.mark.data
def test_excluded_csv_matches_stats():
    import pandas as pd
    ex = pd.read_csv("data/excluded.csv")
    stats = json.loads(Path("data/stats.json").read_text(encoding="utf-8"))
    assert stats["total_including_unknown"] == stats["total_examples"] + len(ex)
    assert stats["excluded"] == ex["reason"].value_counts().to_dict()


@pytest.mark.data
def test_id_map_from_v1_covers_old_rows():
    # Written once by `python -m pipeline.rebuild` when it replaces a
    # pre-2.0 CSV. Lets anyone translate an old example_id to the new one.
    path = Path("data/id_map_v1_to_v2.csv")
    if not path.exists():
        pytest.skip("no id map (dataset was never on v1 IDs)")
    import pandas as pd
    m = pd.read_csv(path)
    assert list(m.columns) == ["old_example_id", "new_example_id", "source_url"]
    assert m["old_example_id"].is_unique
    assert m["old_example_id"].str.match(r"^NF2_\d{8}_\d{4}$").all()
