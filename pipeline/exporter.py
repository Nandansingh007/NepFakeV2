# pipeline/exporter.py
# =============================================================================
# Exports normalized NepFakeV2Example records to CSV, JSON and stats.
#
# Output files:
#   data/nepfakev2.csv   ← research dataset (CSV format)
#   data/nepfakev2.json  ← research dataset (JSON format)
#   data/stats.json      ← dataset statistics
#
# Note:
#   UNKNOWN (-1) records are excluded from CSV and JSON exports.
#   They are counted in stats.json under label_distribution.
#   Each excluded record has annotator_notes = "verdict_unmappable".
#
# Usage:
#   from pipeline.exporter import export
# =============================================================================

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from config.settings import DATA_DIR, LABELS
from schema.schema import NepFakeV2Example, to_dict

logger = logging.getLogger("nepfakev2.exporter")


def export(examples: list[NepFakeV2Example]) -> dict:
    """
    Export normalized examples to CSV, JSON and stats files.

    UNKNOWN (-1) records are excluded from CSV and JSON — they have
    unmappable verdicts and must not enter the research dataset.
    Stats are computed over the full list so unknowns are visible.

    Args:
        examples: List of NepFakeV2Example (may include -1 records)

    Returns:
        Dict with export stats
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not examples:
        logger.warning("No examples to export")
        return {}

    # Exclude UNKNOWN (-1) records from exported dataset
    exportable = [e for e in examples if e.verdict_label != -1]
    unknown_count = len(examples) - len(exportable)
    if unknown_count > 0:
        logger.warning(
            f"{unknown_count} UNKNOWN (-1) records excluded from export "
            f"— check raw verdict strings for manual review"
        )

    # Convert exportable records to dicts
    records = [to_dict(e) for e in exportable]

    # --- Export CSV ---
    csv_path = DATA_DIR / "nepfakev2.csv"
    df = pd.DataFrame(records)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"Exported CSV: {csv_path} ({len(records)} records)")

    # --- Export JSON ---
    json_path = DATA_DIR / "nepfakev2.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"Exported JSON: {json_path} ({len(records)} records)")

    # --- Compute and export stats ---
    # Pass full examples list so unknowns appear in label_distribution
    stats = compute_stats(examples)
    stats_path = DATA_DIR / "stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info(f"Exported stats: {stats_path}")

    return stats


def compute_stats(examples: list[NepFakeV2Example]) -> dict:
    """
    Compute dataset statistics over the full example list.
    Includes UNKNOWN (-1) records so the stats file is honest
    about how many records were excluded from the export.

    Args:
        examples: Full list of NepFakeV2Example (including -1 records)

    Returns:
        Dict with dataset statistics
    """
    total = len(examples)

    # Label distribution
    label_dist = {0: 0, 1: 0, 2: 0, -1: 0}
    for e in examples:
        label_dist[e.verdict_label] = label_dist.get(e.verdict_label, 0) + 1

    # Source distribution
    source_dist = {}
    for e in examples:
        source_dist[e.source_name] = source_dist.get(e.source_name, 0) + 1

    # Topic distribution
    topic_dist = {}
    for e in examples:
        topic_dist[e.topic_category] = topic_dist.get(e.topic_category, 0) + 1

    # Date range
    dates = sorted([
        e.date_published for e in examples
        if e.date_published and len(e.date_published) == 10
    ])

    # Nepali language stats
    nepali_count = sum(1 for e in examples if e.is_native_nepali)

    # Annotator notes stats
    flagged = sum(1 for e in examples if e.annotator_notes)

    stats = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_examples": total - label_dist.get(-1, 0),  # exported count
        "total_including_unknown": total,                  # full count
        "label_distribution": {
            LABELS.get(label, str(label)): {
                "count": count,
                "pct": f"{count/total*100:.1f}%"
            }
            for label, count in sorted(label_dist.items())
            if count > 0
        },
        "source_distribution": {
            source: {
                "count": count,
                "pct": f"{count/total*100:.1f}%"
            }
            for source, count in sorted(
                source_dist.items(), key=lambda x: -x[1]
            )
        },
        "topic_distribution": {
            topic: {
                "count": count,
                "pct": f"{count/total*100:.1f}%"
            }
            for topic, count in sorted(
                topic_dist.items(), key=lambda x: -x[1]
            )
        },
        "date_range": {
            "oldest": dates[0] if dates else "",
            "newest": dates[-1] if dates else "",
            "total_with_date": len(dates),
            "total_without_date": total - len(dates),
        },
        "language": {
            "nepali_script": nepali_count,
            "nepali_pct": f"{nepali_count/total*100:.1f}%",
        },
        "quality": {
            "flagged_for_review": flagged,
            "flagged_pct": f"{flagged/total*100:.1f}%",
        },
        "schema_version": "1.0",
    }

    return stats