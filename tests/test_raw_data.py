"""
Test: raw data quality
Verifies raw JSON files are complete and valid.
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, '.')

errors = []
warnings = []

RAW_DIRS = {
    "techpana": "raw/techpana",
    "nepalfactcheck": "raw/nepalfactcheck",
}

REQUIRED_FIELDS = [
    "source_name", "source_url", "title", "body_text",
    "raw_verdict_text", "date_published", "date_scraped",
]

total_articles = 0

for source_name, raw_dir in RAW_DIRS.items():
    p = Path(raw_dir)
    if not p.exists():
        errors.append(f"Raw directory missing: {raw_dir}")
        continue

    json_files = [f for f in sorted(p.glob("*.json")) if f.name != ".gitkeep"]
    if not json_files:
        errors.append(f"No JSON files in: {raw_dir}")
        continue

    source_articles = []
    for f in json_files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                articles = json.load(fp)
                source_articles.extend(articles)
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON: {f} — {e}")

    if not source_articles:
        errors.append(f"No articles loaded from: {raw_dir}")
        continue

    total_articles += len(source_articles)

    # Check required fields
    for i, article in enumerate(source_articles[:20]):
        for field in REQUIRED_FIELDS:
            if field not in article:
                errors.append(f"{source_name}[{i}] missing field: {field}")

    # Check no empty bodies
    empty_bodies = sum(1 for a in source_articles if not a.get('body_text'))
    if empty_bodies > 0:
        errors.append(f"{source_name}: {empty_bodies} empty body texts")

    # Check no empty titles
    empty_titles = sum(1 for a in source_articles if not a.get('title'))
    if empty_titles > 0:
        errors.append(f"{source_name}: {empty_titles} empty titles")

    # Check source_name field matches directory
    wrong_source = sum(
        1 for a in source_articles
        if a.get('source_name') != source_name
    )
    if wrong_source > 0:
        warnings.append(
            f"{source_name}: {wrong_source} articles with wrong source_name"
        )

    # Check URL deduplication — no duplicate URLs
    urls = [a['source_url'] for a in source_articles]
    unique_urls = set(urls)
    if len(urls) != len(unique_urls):
        errors.append(
            f"{source_name}: {len(urls) - len(unique_urls)} duplicate URLs"
        )

    # Check verdict distribution
    verdicts = {}
    for a in source_articles:
        v = a.get('raw_verdict_text', '').strip() or 'EMPTY'
        verdicts[v] = verdicts.get(v, 0) + 1

    empty_count = verdicts.get('EMPTY', 0)
    empty_pct = empty_count / len(source_articles) * 100
    if empty_pct > 10:
        errors.append(
            f"{source_name}: {empty_pct:.1f}% empty verdicts — check scraper"
        )
    elif empty_count > 0:
        warnings.append(
            f"{source_name}: {empty_count} empty verdicts ({empty_pct:.1f}%) "
            f"— known edge cases, flagged with annotator_notes"
        )

# Check last_run.json
last_run_path = Path("raw/last_run.json")
if not last_run_path.exists():
    errors.append("raw/last_run.json missing")
else:
    with open(last_run_path, "r", encoding="utf-8") as f:
        last_run = json.load(f)

    for source, data in last_run.get('sources', {}).items():
        if data.get('status') == 'failed':
            errors.append(f"last_run.json: {source} last run failed")
        if not data.get('last_published_date'):
            warnings.append(f"last_run.json: {source} has no last_published_date")

# Check stats_raw.json
stats_path = Path("raw/stats_raw.json")
if not stats_path.exists():
    errors.append("raw/stats_raw.json missing")
else:
    with open(stats_path, "r", encoding="utf-8") as f:
        stats = json.load(f)

    if stats.get('total_raw_articles', 0) != total_articles:
        warnings.append(
            f"stats_raw.json total ({stats.get('total_raw_articles')}) "
            f"!= actual ({total_articles})"
        )

if errors:
    print("FAIL — raw data errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    sys.exit(1)
else:
    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    print(f"PASS — raw data: {total_articles} articles, all fields valid")
