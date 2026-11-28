"""Raw stats count articles, not snapshots (28 Nov 2026: a full re-scrape
showed raw 1931 for 972 articles and NepalFactCheck "+690 new" for 2)."""
import json

from pipeline import collector, update_readme


def _write(path, records):
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")


def test_snapshots_counted_once(tmp_path, monkeypatch):
    src = tmp_path / "nepalfactcheck"
    src.mkdir()
    a = {"source_url": "https://nepalfactcheck.org/2024/01/a/", "raw_verdict_text": "भ्रामक सूचना",
         "date_published": "2024-01-02", "date_scraped": "2026-09-12"}
    b = {"source_url": "https://nepalfactcheck.org/2024/01/b", "raw_verdict_text": "मिथ्या सूचना",
         "date_published": "2024-01-03", "date_scraped": "2026-09-12"}
    _write(src / "2026-09-12.json", [a, b])
    # same two articles again (one without trailing slash) + one new; a's verdict changed
    _write(src / "2026-11-28.json", [
        {**a, "source_url": a["source_url"].rstrip("/"), "raw_verdict_text": "अपुष्ट सूचना",
         "date_scraped": "2026-11-28"},
        {**b, "date_scraped": "2026-11-28"},
        {**b, "source_url": "https://nepalfactcheck.org/2026/11/c", "date_scraped": "2026-11-28"},
    ])
    monkeypatch.setattr(collector, "RAW_DIRS", {"nepalfactcheck": src})
    s = collector.compute_raw_stats()
    assert s["total_raw_articles"] == 3
    assert s["total_raw_snapshots"] == 5
    nfc = s["by_source"]["nepalfactcheck"]
    assert nfc["total"] == 3 and nfc["snapshots"] == 5
    # verdict profile from the newest snapshot of each article
    assert nfc["verdict_distribution"] == {"अपुष्ट सूचना": 1, "मिथ्या सूचना": 2}


def test_last_run_line_shows_new_not_fetched(tmp_path, monkeypatch):
    (tmp_path / "last_run.json").write_text(json.dumps({
        "last_run_date": "2026-11-28",
        "sources": {"nepalfactcheck": {"status": "success", "articles_scraped": 690, "new_articles": 2},
                    "techpana": {"status": "success", "articles_scraped": 1}},
    }), encoding="utf-8")
    monkeypatch.setattr(update_readme, "RAW_DIR", tmp_path)
    line = update_readme.format_last_run({})
    assert "+2 new (690 fetched)" in line
    assert "+1 new" in line and "(1 fetched)" not in line   # old last_run.json, no new_articles
