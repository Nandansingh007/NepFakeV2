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
    from utils.helpers import snapshot_files
    first_file = snapshot_files("raw/techpana")[0][0]
    src = json.loads(Path(first_file).read_text(encoding="utf-8"))[0]
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
# Quality guard: a degraded newer snapshot does not replace a good older one
# -----------------------------------------------------------------------------

def _snap(scraped, label_source="conclusion", claim_source="claim_caption",
          evidence="e" * 800, fine="FALSE", url="https://techpana.com/2026/1/a"):
    ex = _ex(url, scraped, fine=fine)
    ex.label_source, ex.claim_source, ex.evidence_text = label_source, claim_source, evidence
    return ex


@pytest.mark.parametrize("newer_kwargs, reason", [
    ({"label_source": "stored"}, "label_source conclusion -> stored"),
    ({"claim_source": "lead"}, "claim_source claim_caption -> lead"),
    ({"evidence": "e" * 300}, "text 800 -> 300 chars"),
])
def test_degraded_newer_snapshot_keeps_older(newer_kwargs, reason):
    from pipeline import deduplicator
    old = _snap("2026-09-12")
    new = _snap("2026-12-14", **newer_kwargs)
    for order in ([old, new], [new, old]):
        kept = deduplicator.deduplicate(order)
        assert len(kept) == 1 and kept[0].date_scraped == "2026-09-12"
        r = deduplicator.LAST_REPORT
        assert r["replaced"] == 0 and r["label_changed"] == []
        assert [c["reasons"] for c in r["kept_older"]] == [[reason]]


def test_better_or_equal_newer_snapshot_replaces_older():
    from pipeline import deduplicator
    old = _snap("2026-09-12", label_source="stored", claim_source="lead", evidence="e" * 400)
    new = _snap("2026-12-14", label_source="conclusion", evidence="e" * 390, fine="MISLEADING")
    kept = deduplicator.deduplicate([old, new])
    assert kept[0].date_scraped == "2026-12-14"
    r = deduplicator.LAST_REPORT
    assert r["kept_older"] == [] and r["replaced"] == 1 and len(r["label_changed"]) == 1


def test_conflict_degraded_newer_with_weaker_label_keeps_older_whole():
    # Rule 3: labels differ and the newer copy is degraded. The stronger
    # label source wins (conclusion > stored); the whole copy is used.
    from pipeline import deduplicator
    old = _snap("2026-09-12", label_source="conclusion", fine="FALSE")
    new = _snap("2026-12-14", label_source="stored", fine="MISLEADING", evidence="x" * 790)
    (kept,) = deduplicator.deduplicate([new, old])
    assert kept is old and kept.evidence_text == "e" * 800        # no field mixing
    assert (kept.snapshot_conflict, kept.snapshot_other_label) == (True, "MISLEADING")
    (c,) = deduplicator.LAST_REPORT["conflicts"]
    assert c["kept"] == "older" and c["old_label"] == "FALSE" and c["new_label"] == "MISLEADING"
    assert deduplicator.LAST_REPORT["label_changed"] == []        # never fails the flip gate


def test_conflict_degraded_newer_with_stronger_label_wins():
    # Old copy labelled by the badge only, new copy reads the conclusion but
    # lost half its text: the new copy's label has stronger evidence.
    from pipeline import deduplicator
    old = _snap("2026-09-12", label_source="stored", fine="MISLEADING", evidence="e" * 800)
    new = _snap("2026-12-14", label_source="conclusion", fine="FALSE", evidence="n" * 300)
    (kept,) = deduplicator.deduplicate([old, new])
    assert kept is new and kept.evidence_text == "n" * 300
    assert (kept.snapshot_conflict, kept.snapshot_other_label) == (True, "MISLEADING")
    assert deduplicator.LAST_REPORT["conflicts"][0]["kept"] == "newer"


def test_conflict_equal_label_strength_keeps_newer():
    from pipeline import deduplicator
    old = _snap("2026-09-12", label_source="conclusion", claim_source="claim_caption", fine="FALSE")
    new = _snap("2026-12-14", label_source="conclusion", claim_source="lead", fine="MISLEADING")
    (kept,) = deduplicator.deduplicate([old, new])
    assert kept is new and kept.snapshot_other_label == "FALSE"
    assert "equal" in deduplicator.LAST_REPORT["conflicts"][0]["rule"]


def test_plain_label_change_is_flagged_too():
    # Rule 1: a complete newer copy wins; the row still says another
    # snapshot disagreed, and the flip gate still counts it.
    from pipeline import deduplicator
    old = _snap("2026-09-12", fine="FALSE")
    new = _snap("2026-12-14", fine="MISLEADING")
    (kept,) = deduplicator.deduplicate([old, new])
    assert kept is new and kept.snapshot_conflict and kept.snapshot_other_label == "FALSE"
    assert len(deduplicator.LAST_REPORT["label_changed"]) == 1


def test_same_label_snapshots_are_not_flagged():
    from pipeline import deduplicator
    (kept,) = deduplicator.deduplicate([_snap("2026-09-12"), _snap("2026-12-14")])
    assert (kept.snapshot_conflict, kept.snapshot_other_label) == (False, "")
    assert deduplicator.LAST_REPORT["conflicts"] == []


def test_third_snapshot_is_compared_with_the_kept_copy():
    from pipeline import deduplicator
    good = _snap("2026-09-12")
    bad = _snap("2026-12-14", label_source="stored")
    good_again = _snap("2026-12-21")
    kept = deduplicator.deduplicate([good, bad, good_again])
    assert kept[0].date_scraped == "2026-12-21"
    assert len(deduplicator.LAST_REPORT["kept_older"]) == 1


def test_newer_snapshot_without_verdict_keeps_older(tmp_path, monkeypatch):
    # The case from the first full re-scrape (29 TechPana pages without a
    # verdict): the newer snapshot is excluded, the older row stays, and the
    # case is reported instead of disappearing.
    import json
    from pipeline import normalizer
    body = ("तथ्य जाँच\nसामाजिक सञ्जालमा एउटा भिडिओ भाइरल भएको छ जुन पुरानो हो।\n"
            "दाबी\nक्याप्सनमा ‘यो भिडिओ हिजो काठमाडौंमा खिचिएको हो भन्दै धेरैले सेयर गरेका छन्’ लेखिएको छ।\n"
            "निष्कर्ष\nयो दाबी भ्रामक हो।\n") * 3
    rec = {"source_name": "techpana", "source_url": "https://techpana.com/2025/123456/x",
           "title": "भिडिओबारे भ्रामक दाबी", "body_text": body, "raw_verdict_text": "भ्रामक",
           "date_published": "2025-05-01"}
    d = tmp_path / "techpana"
    d.mkdir()
    (d / "2026-09-12.json").write_text(json.dumps([rec], ensure_ascii=False), encoding="utf-8")
    lost = {**rec, "body_text": body.replace("भ्रामक", ""), "raw_verdict_text": ""}
    lost["title"] = "भिडिओबारे दाबी"
    (d / "2026-12-14.json").write_text(json.dumps([lost], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(normalizer, "RAW_DIRS", {"techpana": d})
    # normalize_all() fills module-level lists that other tests read
    monkeypatch.setattr(normalizer, "LAST_EXCLUSIONS", [])
    monkeypatch.setattr(normalizer, "LAST_SHADOWED", [])
    kept = normalizer.normalize_all(references={}, claims={})
    assert [e.date_scraped for e in kept] == ["2026-09-12"]
    assert normalizer.LAST_EXCLUSIONS == []
    assert [(x["reason"], x["date_scraped"], x["kept_scraped"]) for x in normalizer.LAST_SHADOWED] \
        == [("verdict_unmappable", "2026-12-14", "2026-09-12")]


@pytest.mark.data
def test_rescrape_did_not_degrade_many_articles():
    # Gate for re-scrapes: the guard above keeps the older copy, so no data is
    # lost, but if a large share of re-scraped articles came back worse (or
    # without a verdict), the scraper is broken and the run should be looked
    # at before it is committed. 20% per source; at least 5 always allowed.
    # (The first full re-scrape had about 28 of ~280 TechPana pages without
    # a verdict, so 10% would have been too tight to pass on a known case.)
    from pipeline import deduplicator, normalizer
    deduplicator.deduplicate(normalizer.normalize_all())   # fresh LAST_SHADOWED
    r = deduplicator.LAST_REPORT
    bad = {}
    for case in r["kept_older"]:
        bad[case["source_name"]] = bad.get(case["source_name"], 0) + 1
    for x in normalizer.LAST_SHADOWED:
        bad[x["source_name"]] = bad.get(x["source_name"], 0) + 1
    if not r["rescraped"] and not bad:
        pytest.skip("no URL has two snapshots yet")
    for name, n in bad.items():
        total = r["rescraped"].get(name, 0) + sum(
            1 for x in normalizer.LAST_SHADOWED if x["source_name"] == name)
        assert n <= max(5, 0.20 * total), (name, n, total, r["kept_older"][:5],
                                           normalizer.LAST_SHADOWED[:5])


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
