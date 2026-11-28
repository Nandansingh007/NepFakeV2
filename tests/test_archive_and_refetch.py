"""
28 Nov 2026 fixes:
  - raw/archive/: older raw files moved byte for byte after a full re-scrape,
    still read by the pipeline (snapshot_source "archive")
  - a full re-scrape fetches directly the known articles the listing no
    longer shows (e.g. TechPana 159035), and never fetches one URL twice
"""
import csv
import json

import pytest

from pipeline import archive, normalizer
from utils.helpers import snapshot_files


def _write(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def test_archive_moves_files_unchanged(tmp_path):
    live = tmp_path / "raw" / "techpana"
    _write(live / "2026-09-12.json", [{"a": 1}])
    _write(live / "2026-11-28.json", [{"a": 2}])
    before = (live / "2026-09-12.json").read_bytes()
    manifest = tmp_path / "raw" / "archive" / "MANIFEST.csv"
    moved = archive.archive_older("techpana", "2026-11-28", raw_dir=live,
                                  manifest=manifest, today="2026-11-28")
    assert moved == ["2026-09-12.json"]
    assert [f.name for f in live.glob("*.json")] == ["2026-11-28.json"]
    archived = tmp_path / "raw" / "archive" / "techpana" / "2026-09-12.json"
    assert archived.read_bytes() == before
    row = list(csv.DictReader(open(manifest, encoding="utf-8")))[0]
    assert row["sha256"] == archive.sha256(archived)
    assert row["full_rescrape_file"] == "2026-11-28.json"
    # running it again changes nothing
    assert archive.archive_older("techpana", "2026-11-28", raw_dir=live, manifest=manifest) == []
    # live and archive are both read, oldest first
    assert [(f.name, w) for f, w in snapshot_files(live)] == [
        ("2026-09-12.json", "archive"), ("2026-11-28.json", "live")]


def test_archive_never_overwrites_different_bytes(tmp_path):
    live = tmp_path / "raw" / "techpana"
    _write(live / "2026-09-12.json", [{"a": 1}])
    _write(tmp_path / "raw" / "archive" / "techpana" / "2026-09-12.json", [{"a": "other"}])
    with pytest.raises(RuntimeError):
        archive.archive_older("techpana", "2026-11-28", raw_dir=live,
                              manifest=tmp_path / "m.csv")
    assert (live / "2026-09-12.json").exists()


def test_archived_copy_used_only_when_live_has_none(tmp_path, monkeypatch):
    nfc = tmp_path / "raw" / "nepalfactcheck"
    body = "☰\n×\nभ्रामक सूचना\nनेताको भनिएको भिडिओ\nHome\n" + \
        "सामाजिक सञ्जालमा नेताले भाषण गरेको दाबीसहित भिडिओ भाइरल भएको छ ।\n" * 5
    rec = lambda url, d: {"source_name": "nepalfactcheck", "source_url": url, "title": "नेताको भिडिओ",
                          "body_text": body, "raw_verdict_text": "भ्रामक सूचना",
                          "date_published": "2024-01-02", "date_scraped": d}
    _write(tmp_path / "raw" / "archive" / "nepalfactcheck" / "2026-09-12.json",
           [rec("https://nepalfactcheck.org/2024/01/a", "2026-09-12"),
            rec("https://nepalfactcheck.org/2024/01/b", "2026-09-12")])
    _write(nfc / "2026-11-28.json", [rec("https://nepalfactcheck.org/2024/01/a", "2026-11-28")])
    monkeypatch.setattr(normalizer, "RAW_DIRS", {"nepalfactcheck": nfc})
    from pipeline.deduplicator import deduplicate
    kept = {e.source_url: e for e in deduplicate(normalizer.normalize_all({}, {}))}
    assert kept["https://nepalfactcheck.org/2024/01/a"].snapshot_source == "live"
    assert kept["https://nepalfactcheck.org/2024/01/b"].snapshot_source == "archive"


from scrapers.base import BaseScraper


class _FakeScraper(BaseScraper):
    """BaseScraper.paginate / refetch_unlisted with the network replaced."""

    def __init__(self, pages, known, gone=()):   # no super(): no session, no FlareSolverr
        import logging
        self.logger = logging.getLogger("test")
        self.source_name = "techpana"
        self.config = {"start_page": 1, "list_url_template": "p{page}"}
        self.last_published_date = None
        self.articles_scraped = self.articles_skipped = self.unlisted_refetched = 0
        self.pages, self.fetched, self._known, self._gone = pages, [], known, set(gone)

    def get_article_links(self, page_url):
        return self.pages.get(page_url, [])

    def scrape_article(self, url):
        from schema.schema import RawArticle
        self.fetched.append(url)
        if url in self._gone or "news" in url:
            return None
        return RawArticle(source_name="techpana", source_url=url, title="t", body_text="b",
                          raw_verdict_text="", date_published="", date_scraped="2026-11-28")

    def known_urls(self):
        return {u.rstrip("/"): u for u in self._known}


def test_paginate_fetches_each_url_once_and_refetches_unlisted(monkeypatch):
    monkeypatch.setenv("NEPFAKE_FULL_RESCRAPE", "1")
    news = "https://techpana.com/2026/1/news"           # sidebar card on every page
    pages = {"p1": [("https://techpana.com/2026/10/a", ""), (news, "")],
             "p2": [("https://techpana.com/2026/9/b", ""), (news, "")]}
    s = _FakeScraper(pages, known=["https://techpana.com/2026/10/a",
                                   "https://techpana.com/2026/159035/unlisted",
                                   "https://techpana.com/2026/2/deleted"],
                     gone=["https://techpana.com/2026/2/deleted"])
    out = s.paginate()
    assert s.fetched.count(news) == 1
    assert {a.source_url for a in out} == {"https://techpana.com/2026/10/a",
                                           "https://techpana.com/2026/9/b",
                                           "https://techpana.com/2026/159035/unlisted"}
    assert s.unlisted_refetched == 1


def test_incremental_run_does_not_refetch_unlisted(monkeypatch):
    monkeypatch.delenv("NEPFAKE_FULL_RESCRAPE", raising=False)
    s = _FakeScraper({"p1": [("https://techpana.com/2026/10/a", "")]},
                     known=["https://techpana.com/2026/159035/unlisted"])
    s.paginate()
    assert s.fetched == ["https://techpana.com/2026/10/a"]


def test_weekly_run_keeps_cutoff_day_and_skips_known(monkeypatch):
    # last run's newest article was from 2026-11-23; another article of that
    # day appeared after the run. It must be fetched; the known one must not.
    monkeypatch.delenv("NEPFAKE_FULL_RESCRAPE", raising=False)
    pages = {"p1": [("https://nepalfactcheck.org/2026/11/new", "2026-11-25"),
                    ("https://nepalfactcheck.org/2026/11/same-day-late", "2026-11-23"),
                    ("https://nepalfactcheck.org/2026/11/same-day-known", "2026-11-23"),
                    ("https://nepalfactcheck.org/2026/11/old", "2026-11-20"),
                    ("https://nepalfactcheck.org/2026/11/older", "2026-11-19")]}
    s = _FakeScraper(pages, known=["https://nepalfactcheck.org/2026/11/same-day-known"])
    s.last_published_date = "2026-11-23"
    s.paginate()
    assert s.fetched == ["https://nepalfactcheck.org/2026/11/new",
                         "https://nepalfactcheck.org/2026/11/same-day-late"]


def test_workflow_env_counts_as_full_rescrape(monkeypatch):
    # weekly_scrape.yml sets NEPFAKE_FULL_RESCRAPE=1 and calls the collector
    # without --full; the archive step must still run.
    import inspect
    from pipeline import collector
    src = inspect.getsource(collector.run_collector)
    assert 'os.environ.get("NEPFAKE_FULL_RESCRAPE") == "1"' in src
