# check_raw.py
# =============================================================================
# Raw data quality report — run after every scrape.
# Prints statistics about raw JSON files in raw/.
# Not a pass/fail test — a diagnostic report to spot problems early.
#
# Usage:
#   python check_raw.py
# =============================================================================

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

sys.path.insert(0, '.')

RAW_DIRS = {
    "techpana":       Path("raw/techpana"),
    "nepalfactcheck": Path("raw/nepalfactcheck"),
}

EMPTY_VERDICT_THRESHOLD_PCT = 10.0   # warn if > 10% empty verdicts
MIN_BODY_LENGTH = 100                 # warn if body < 100 chars
DATE_FLOOR = "2020-01-01"            # warn if oldest date before this
DATE_CEILING = "2030-01-01"          # warn if newest date after this

SEP = "=" * 60


def load_source(raw_dir: Path) -> list[dict]:
    articles = []
    for json_file in sorted(raw_dir.glob("*.json")):
        if json_file.name == ".gitkeep":
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                batch = json.load(f)
                articles.extend(batch)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ERROR reading {json_file.name}: {e}")
    return articles


def check_source(source_name: str, articles: list[dict]) -> list[str]:
    """Run quality checks. Returns list of warning strings."""
    warnings = []

    if not articles:
        warnings.append("NO ARTICLES — directory empty or all files unreadable")
        return warnings

    total = len(articles)

    # --- Verdict distribution ---
    verdicts = Counter(
        (a.get("raw_verdict_text", "") or "EMPTY").strip() or "EMPTY"
        for a in articles
    )
    empty_count = verdicts.get("EMPTY", 0)
    empty_pct = empty_count / total * 100
    if empty_pct > EMPTY_VERDICT_THRESHOLD_PCT:
        warnings.append(
            f"HIGH empty verdicts: {empty_count}/{total} ({empty_pct:.1f}%) "
            f"— threshold {EMPTY_VERDICT_THRESHOLD_PCT}%"
        )

    # --- Body length ---
    short_bodies = [
        a for a in articles
        if len((a.get("body_text") or "").strip()) < MIN_BODY_LENGTH
    ]
    if short_bodies:
        warnings.append(
            f"{len(short_bodies)} articles with body < {MIN_BODY_LENGTH} chars"
        )

    # --- Duplicate URLs ---
    urls = [a.get("source_url", "") for a in articles]
    dupes = len(urls) - len(set(urls))
    if dupes > 0:
        warnings.append(f"{dupes} duplicate source URLs")

    # --- Date range (ISO dates only) ---
    iso_dates = sorted([
        a.get("date_published", "")[:10]
        for a in articles
        if a.get("date_published", "")
        and a.get("date_published", "")[0].isdigit()
        and len(a.get("date_published", "")) >= 10
    ])
    if iso_dates:
        if iso_dates[0] < DATE_FLOOR:
            warnings.append(f"Oldest date {iso_dates[0]} is before {DATE_FLOOR}")
        if iso_dates[-1] > DATE_CEILING:
            warnings.append(f"Newest date {iso_dates[-1]} is after {DATE_CEILING}")

    # --- Missing required fields ---
    required = ["source_name", "source_url", "title", "body_text",
                "raw_verdict_text", "date_published", "date_scraped"]
    for field in required:
        missing = sum(1 for a in articles if not a.get(field))
        if missing > 0:
            warnings.append(f"{missing} articles missing field: '{field}'")

    return warnings


def print_source_report(source_name: str, articles: list[dict]):
    total = len(articles)
    print(f"\nSource: {source_name.upper()}")
    print(f"  Total articles : {total}")

    if not articles:
        print("  NO DATA")
        return

    # Verdict distribution
    verdicts = Counter(
        (a.get("raw_verdict_text", "") or "EMPTY").strip() or "EMPTY"
        for a in articles
    )
    print(f"  Verdict distribution:")
    for verdict, count in sorted(verdicts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"    {verdict:<20} {count:>4}  ({pct:5.1f}%)  {bar}")

    # Date range
    iso_dates = sorted([
        a.get("date_published", "")[:10]
        for a in articles
        if a.get("date_published", "")
        and a.get("date_published", "")[0].isdigit()
        and len(a.get("date_published", "")) >= 10
    ])
    bs_dates = [
        a for a in articles
        if a.get("date_published", "")
        and not a.get("date_published", "")[0].isdigit()
    ]
    if iso_dates:
        print(f"  Date range     : {iso_dates[0]} → {iso_dates[-1]}")
    if bs_dates:
        print(f"  BS dates       : {len(bs_dates)} (converted in Stage 2)")
    no_date = sum(1 for a in articles if not a.get("date_published"))
    if no_date:
        print(f"  Missing dates  : {no_date}")

    # Body length stats
    body_lengths = [len((a.get("body_text") or "").strip()) for a in articles]
    if body_lengths:
        avg = sum(body_lengths) / len(body_lengths)
        print(f"  Body length    : avg {avg:.0f} chars, "
              f"min {min(body_lengths)}, max {max(body_lengths)}")

    # Devanagari coverage
    def has_devanagari(text):
        return any("\u0900" <= c <= "\u097F" for c in (text or ""))

    nepali_count = sum(
        1 for a in articles if has_devanagari(a.get("title", ""))
    )
    print(f"  Devanagari     : {nepali_count}/{total} ({nepali_count/total*100:.1f}%)")

    # Annotator notes
    flagged = sum(1 for a in articles if a.get("annotator_notes"))
    if flagged:
        print(f"  Flagged        : {flagged} articles have annotator_notes")

    # Files on disk
    raw_dir = RAW_DIRS[source_name]
    json_files = [f for f in sorted(raw_dir.glob("*.json"))
                  if f.name != ".gitkeep"]
    print(f"  JSON files     : {len(json_files)} "
          f"({', '.join(f.name for f in json_files[-3:])}...)"
          if len(json_files) > 3
          else f"  JSON files     : {len(json_files)} "
               f"({', '.join(f.name for f in json_files)})")

    # Warnings
    warnings = check_source(source_name, articles)
    if warnings:
        print(f"  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"    ⚠  {w}")
    else:
        print(f"  Quality        : OK — no warnings")


def print_last_run():
    last_run_path = Path("raw/last_run.json")
    if not last_run_path.exists():
        print("\n  last_run.json  : NOT FOUND")
        return

    with open(last_run_path, "r", encoding="utf-8") as f:
        last_run = json.load(f)

    print(f"\nLast run       : {last_run.get('last_run_date', 'unknown')}")
    print(f"Run ID         : {last_run.get('run_id', 'unknown')}")
    for source, data in last_run.get("sources", {}).items():
        status = data.get("status", "unknown")
        count = data.get("articles_scraped", 0)
        last_pub = data.get("last_published_date", "unknown")
        flag = "✓" if status == "success" else "✗"
        print(f"  {flag} {source:<20} {count:>4} new | "
              f"last_published: {last_pub} | status: {status}")
        if data.get("error"):
            print(f"    ERROR: {data['error']}")


def main():
    print(SEP)
    print("NepFakeV2 — Raw Data Quality Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)

    print_last_run()

    all_articles = []
    for source_name, raw_dir in RAW_DIRS.items():
        if not raw_dir.exists():
            print(f"\nSource: {source_name.upper()}")
            print(f"  MISSING — {raw_dir} does not exist")
            continue
        articles = load_source(raw_dir)
        all_articles.extend(articles)
        print_source_report(source_name, articles)

    # Combined summary
    print(f"\n{SEP}")
    print(f"COMBINED TOTAL : {len(all_articles)} raw articles")

    all_verdicts = Counter(
        (a.get("raw_verdict_text", "") or "EMPTY").strip() or "EMPTY"
        for a in all_articles
    )
    empty_total = all_verdicts.get("EMPTY", 0)
    print(f"Empty verdicts : {empty_total} ({empty_total/len(all_articles)*100:.1f}%)"
          if all_articles else "Empty verdicts : N/A")

    all_warnings = []
    for source_name, raw_dir in RAW_DIRS.items():
        if raw_dir.exists():
            articles = load_source(raw_dir)
            all_warnings.extend(check_source(source_name, articles))

    if all_warnings:
        print(f"\nTotal warnings : {len(all_warnings)} — review before Stage 2")
    else:
        print(f"Quality        : OK — all sources clean")
    print(SEP)


if __name__ == "__main__":
    main()