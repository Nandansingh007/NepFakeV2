# check_clean.py
# =============================================================================
# Clean data quality report — run after every pipeline export.
# Prints statistics about data/nepfakev2.csv and data/stats.json.
# Not a pass/fail test — a diagnostic report to spot problems early.
#
# Usage:
#   python check_clean.py
# =============================================================================

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

import pandas as pd

sys.path.insert(0, '.')

DATA_DIR = Path("data")
SEP = "=" * 60

# Thresholds — adjust as dataset grows
MIN_ROWS              = 900
MAX_UNKNOWN_PCT       = 0.0    # -1 must never appear in CSV
MIN_NEPALI_PCT        = 90.0   # at least 90% Devanagari
MAX_MISSING_DATE_PCT  = 5.0    # warn if > 5% missing dates
EXPECTED_SOURCES      = {"techpana", "nepalfactcheck"}
DEAD_SOURCES          = {"nepalcheck", "bbc_nepali", "kantipur", "misinfonepal"}


def load_csv() -> pd.DataFrame | None:
    csv_path = DATA_DIR / "nepfakev2.csv"
    if not csv_path.exists():
        print(f"  ERROR: {csv_path} not found — run pipeline first")
        return None
    return pd.read_csv(csv_path)


def load_stats() -> dict | None:
    stats_path = DATA_DIR / "stats.json"
    if not stats_path.exists():
        print(f"  ERROR: stats.json not found")
        return None
    with open(stats_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json() -> list | None:
    json_path = DATA_DIR / "nepfakev2.json"
    if not json_path.exists():
        print(f"  ERROR: nepfakev2.json not found")
        return None
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_label_distribution(df: pd.DataFrame):
    label_map = {0: "REAL", 1: "FALSE_MISLEADING", 2: "UNVERIFIED", -1: "UNKNOWN"}
    total = len(df)
    print(f"\n  Label distribution ({total} total):")
    counts = df["verdict_label"].value_counts().sort_index()
    for label, count in counts.items():
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        name = label_map.get(int(label), str(label))
        print(f"    {name:<20} {count:>4}  ({pct:5.1f}%)  {bar}")


def print_source_distribution(df: pd.DataFrame):
    total = len(df)
    print(f"\n  Source distribution:")
    counts = df["source_name"].value_counts()
    for source, count in counts.items():
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"    {source:<20} {count:>4}  ({pct:5.1f}%)  {bar}")


def print_topic_distribution(df: pd.DataFrame):
    total = len(df)
    print(f"\n  Topic distribution:")
    counts = df["topic_category"].value_counts()
    for topic, count in counts.items():
        pct = count / total * 100
        print(f"    {topic:<20} {count:>4}  ({pct:5.1f}%)")


def print_date_stats(df: pd.DataFrame):
    total = len(df)
    valid_dates = df["date_published"].dropna()
    valid_dates = valid_dates[valid_dates.astype(str).str.len() >= 10]
    missing = total - len(valid_dates)
    print(f"\n  Date coverage:")
    print(f"    With date      : {len(valid_dates)}/{total} "
          f"({len(valid_dates)/total*100:.1f}%)")
    if missing:
        print(f"    Missing date   : {missing} ({missing/total*100:.1f}%)")
    if len(valid_dates):
        sorted_dates = sorted(valid_dates.astype(str))
        print(f"    Oldest         : {sorted_dates[0]}")
        print(f"    Newest         : {sorted_dates[-1]}")


def check_warnings(df: pd.DataFrame) -> list[str]:
    warnings = []
    total = len(df)

    # Row count
    if total < MIN_ROWS:
        warnings.append(
            f"Only {total} rows — expected {MIN_ROWS}+"
        )

    # No -1 in CSV
    if "verdict_label" in df.columns:
        unknown = (df["verdict_label"] == -1).sum()
        if unknown > 0:
            warnings.append(
                f"{unknown} UNKNOWN (-1) records in CSV — "
                f"exporter should have filtered these"
            )

    # Devanagari coverage
    if "is_native_nepali" in df.columns:
        nepali_pct = df["is_native_nepali"].mean() * 100
        if nepali_pct < MIN_NEPALI_PCT:
            warnings.append(
                f"Only {nepali_pct:.1f}% Devanagari — "
                f"expected {MIN_NEPALI_PCT}%+"
            )

    # Duplicate example_ids
    if "example_id" in df.columns:
        dupes = df["example_id"].duplicated().sum()
        if dupes > 0:
            warnings.append(f"{dupes} duplicate example_ids")

    # Dead sources
    if "source_name" in df.columns:
        found_dead = DEAD_SOURCES & set(df["source_name"].unique())
        if found_dead:
            warnings.append(f"Dead sources in dataset: {found_dead}")

    # Missing dates
    if "date_published" in df.columns:
        missing_dates = df["date_published"].isna().sum()
        missing_pct = missing_dates / total * 100
        if missing_pct > MAX_MISSING_DATE_PCT:
            warnings.append(
                f"{missing_dates} missing dates ({missing_pct:.1f}%) — "
                f"threshold {MAX_MISSING_DATE_PCT}%"
            )

    # Empty evidence
    if "evidence_text" in df.columns:
        empty_ev = df["evidence_text"].isna().sum()
        if empty_ev > 0:
            warnings.append(f"{empty_ev} empty evidence_text fields")

    # Label imbalance — warn if any label > 95% of total
    if "verdict_label" in df.columns:
        counts = df["verdict_label"].value_counts()
        for label, count in counts.items():
            pct = count / total * 100
            if pct > 95:
                warnings.append(
                    f"Label {label} is {pct:.1f}% of dataset — severe imbalance"
                )

    # CSV vs JSON count mismatch
    json_data = load_json()
    if json_data is not None and len(json_data) != total:
        warnings.append(
            f"CSV ({total}) and JSON ({len(json_data)}) counts differ"
        )

    return warnings


def print_stats_summary(stats: dict):
    print(f"\n  stats.json summary:")
    print(f"    total_examples         : {stats.get('total_examples', 'N/A')}")
    print(f"    total_including_unknown: {stats.get('total_including_unknown', 'N/A')}")
    print(f"    schema_version         : {stats.get('schema_version', 'N/A')}")
    print(f"    last_updated           : {stats.get('last_updated', 'N/A')}")

    date_range = stats.get("date_range", {})
    if date_range:
        print(f"    date_range             : "
              f"{date_range.get('oldest')} → {date_range.get('newest')}")
        print(f"    with_date              : {date_range.get('total_with_date')}")
        print(f"    without_date           : {date_range.get('total_without_date')}")

    lang = stats.get("language", {})
    if lang:
        print(f"    nepali_script          : "
              f"{lang.get('nepali_script')} ({lang.get('nepali_pct')})")

    quality = stats.get("quality", {})
    if quality:
        print(f"    flagged_for_review     : "
              f"{quality.get('flagged_for_review')} ({quality.get('flagged_pct')})")

    # Staleness check
    last_updated = stats.get("last_updated", "")
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
            hours_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
            if hours_ago > 48:
                print(f"    ⚠  Last updated {hours_ago:.0f} hours ago — may be stale")
        except Exception:
            pass


def main():
    print(SEP)
    print("NepFakeV2 — Clean Data Quality Report")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(SEP)

    df = load_csv()
    if df is None:
        sys.exit(1)

    total = len(df)
    print(f"\nDataset        : {total} examples")
    print(f"Columns        : {list(df.columns)}")

    print_label_distribution(df)
    print_source_distribution(df)
    print_topic_distribution(df)
    print_date_stats(df)

    stats = load_stats()
    if stats:
        print_stats_summary(stats)

    # Warnings
    warnings = check_warnings(df)
    print(f"\n{SEP}")
    if warnings:
        print(f"WARNINGS ({len(warnings)}) — review before launch:")
        for w in warnings:
            print(f"  ⚠  {w}")
    else:
        print("Quality        : OK — no warnings")
    print(SEP)


if __name__ == "__main__":
    main()