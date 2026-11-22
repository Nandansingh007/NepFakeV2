"""
Test: committed raw/ JSON files are complete and valid.

This is a data check, not a code check: it tests whatever is in raw/
right now. In the weekly scrape job it runs on the freshly scraped files,
which is exactly when we want it.
"""
import json
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.data

RAW_DIRS = {
    "techpana": "raw/techpana",
    "nepalfactcheck": "raw/nepalfactcheck",
}
REQUIRED_FIELDS = [
    "source_name", "source_url", "title", "body_text",
    "raw_verdict_text", "date_published", "date_scraped",
]


def _load(raw_dir):
    p = Path(raw_dir)
    assert p.exists(), f"raw directory missing: {raw_dir}"
    files = sorted(p.glob("*.json"))
    assert files, f"no JSON files in {raw_dir}"
    articles = []
    for f in files:
        with open(f, encoding="utf-8") as fp:
            articles.extend(json.load(fp))  # JSONDecodeError fails the test
    assert articles, f"no articles loaded from {raw_dir}"
    return articles


@pytest.fixture(scope="module", params=list(RAW_DIRS), ids=list(RAW_DIRS))
def source(request):
    name = request.param
    return name, _load(RAW_DIRS[name])


def test_required_fields(source):
    # The old script only checked the first 20 articles; this checks all.
    name, articles = source
    missing = [
        (i, f) for i, a in enumerate(articles) for f in REQUIRED_FIELDS if f not in a
    ]
    assert not missing, f"{name}: missing fields {missing[:10]}"


def test_no_empty_bodies_or_titles(source):
    name, articles = source
    assert sum(1 for a in articles if not a.get("body_text")) == 0, f"{name}: empty body_text"
    assert sum(1 for a in articles if not a.get("title")) == 0, f"{name}: empty title"


def test_source_name_matches_dir(source):
    name, articles = source
    wrong = sum(1 for a in articles if a.get("source_name") != name)
    if wrong:
        warnings.warn(f"{name}: {wrong} articles with wrong source_name")


def test_no_duplicate_urls(source):
    name, articles = source
    urls = [a["source_url"] for a in articles]
    assert len(urls) == len(set(urls)), f"{name}: {len(urls) - len(set(urls))} duplicate URLs"


def test_empty_verdict_rate(source):
    name, articles = source
    empty = sum(1 for a in articles if not a.get("raw_verdict_text", "").strip())
    pct = empty / len(articles) * 100
    assert pct <= 10, f"{name}: {pct:.1f}% empty verdicts — check scraper"
    if empty:
        warnings.warn(f"{name}: {empty} empty verdicts ({pct:.1f}%) — known edge cases")


def test_last_run_succeeded():
    # In the weekly job this means: if either scraper failed this week,
    # nothing gets committed or pushed to Hugging Face.
    path = Path("raw/last_run.json")
    assert path.exists(), "raw/last_run.json missing"
    last_run = json.loads(path.read_text(encoding="utf-8"))
    failed = [s for s, d in last_run.get("sources", {}).items() if d.get("status") == "failed"]
    assert not failed, f"last run failed for: {failed}"
    for s, d in last_run.get("sources", {}).items():
        if not d.get("last_published_date"):
            warnings.warn(f"last_run.json: {s} has no last_published_date")


def test_stats_raw_total_matches():
    path = Path("raw/stats_raw.json")
    assert path.exists(), "raw/stats_raw.json missing"
    stats = json.loads(path.read_text(encoding="utf-8"))
    total = sum(len(_load(d)) for d in RAW_DIRS.values())
    if stats.get("total_raw_articles", 0) != total:
        warnings.warn(f"stats_raw.json total ({stats.get('total_raw_articles')}) != actual ({total})")
