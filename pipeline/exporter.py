# pipeline/exporter.py
# =============================================================================
# Exports normalized NepFakeV2Example records to CSV, JSON and stats.
#
# Output files:
#   data/nepfakev2.csv   ← research dataset (CSV format)
#   data/nepfakev2.json  ← research dataset (JSON format)
#   data/stats.json      ← dataset statistics
#   data/excluded.csv    ← articles left out, with the reason (schema 2.0)
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

from config.settings import DATA_DIR, LABELS, SCHEMA_VERSION
from schema.schema import COLUMNS, NepFakeV2Example, to_dict

EXCLUDED_COLUMNS = ["source_name", "source_url", "reason", "date_scraped"]

logger = logging.getLogger("nepfakev2.exporter")


def export(examples: list[NepFakeV2Example], exclusions: list[dict] = None,
           out_dir=None, fixed_timestamp: str = None) -> dict:
    """
    Export normalized examples to CSV, JSON and stats files.

    UNKNOWN (-1) records are excluded from CSV and JSON — they have
    unmappable verdicts and must not enter the research dataset.
    Stats are computed over the full list so unknowns are visible.

    Args:
        examples:   List of NepFakeV2Example (may include -1 records)
        exclusions: articles left out, [{source_name, source_url, reason,
                    date_scraped}] (pipeline.normalizer.LAST_EXCLUSIONS)
        out_dir:    folder to write to (default data/; tests use a temp dir)
        fixed_timestamp: last_updated value (reproducibility test)

    Returns:
        Dict with export stats
    """
    from pathlib import Path
    out = Path(out_dir) if out_dir else DATA_DIR
    out.mkdir(parents=True, exist_ok=True)
    exclusions = list(exclusions or [])

    if not examples:
        logger.warning("No examples to export")
        return {}

    # Exclude UNKNOWN (-1) records from exported dataset
    exportable = [e for e in examples if e.verdict_label != -1]
    for e in examples:
        if e.verdict_label == -1:
            exclusions.append({"source_name": e.source_name, "source_url": e.source_url,
                               "reason": "verdict_unmappable", "date_scraped": e.date_scraped})
    unknown_count = len(examples) - len(exportable)
    if unknown_count > 0:
        logger.warning(
            f"{unknown_count} UNKNOWN (-1) records excluded from export "
            f"— check raw verdict strings for manual review"
        )

    # Convert exportable records to dicts
    records = [to_dict(e) for e in exportable]

    # --- Export CSV ---
    csv_path = out / "nepfakev2.csv"
    df = pd.DataFrame(records, columns=COLUMNS)
    # lineterminator / newline="\n": same bytes on Windows and Linux (CI),
    # otherwise a local rebuild on Windows rewrites every line as CRLF
    df.to_csv(csv_path, index=False, encoding="utf-8-sig", lineterminator="\n")
    logger.info(f"Exported CSV: {csv_path} ({len(records)} records)")

    # --- Export JSON ---
    json_path = out / "nepfakev2.json"
    with open(json_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    logger.info(f"Exported JSON: {json_path} ({len(records)} records)")

    # --- Compute and export stats ---
    # Pass full examples list so unknowns appear in label_distribution
    excluded_path = out / "excluded.csv"
    pd.DataFrame(exclusions, columns=EXCLUDED_COLUMNS).to_csv(
        excluded_path, index=False, encoding="utf-8-sig", lineterminator="\n")
    logger.info(f"Exported exclusions: {excluded_path} ({len(exclusions)} records)")

    stats = compute_stats(exportable, exclusions)
    if fixed_timestamp:
        stats["last_updated"] = fixed_timestamp
    stats_path = out / "stats.json"
    with open(stats_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    logger.info(f"Exported stats: {stats_path}")

    return stats


def compute_stats(examples: list[NepFakeV2Example], exclusions: list[dict] = None) -> dict:
    """
    Compute dataset statistics over the full example list.
    Includes UNKNOWN (-1) records so the stats file is honest
    about how many records were excluded from the export.

    Args:
        examples: Full list of NepFakeV2Example (including -1 records)

    Returns:
        Dict with dataset statistics
    """
    total = len(examples) or 1
    exclusions = exclusions or []
    excluded = {}
    for x in exclusions:
        excluded[x["reason"]] = excluded.get(x["reason"], 0) + 1

    def _dist(attr):
        out = {}
        for e in examples:
            key = getattr(e, attr) or "unset"
            out[key] = out.get(key, 0) + 1
        return dict(sorted(out.items(), key=lambda x: -x[1]))

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

    # Where each verdict was read (label_source)
    label_source_dist = {}
    for e in examples:
        key = e.label_source or "unset"
        label_source_dist[key] = label_source_dist.get(key, 0) + 1

    # Fine labels (schema 2.0), overall and per source
    fine_dist, fine_by_source = {}, {}
    for e in examples:
        key = e.label_fine or "unset"
        fine_dist[key] = fine_dist.get(key, 0) + 1
        per = fine_by_source.setdefault(e.source_name, {})
        per[key] = per.get(key, 0) + 1

    # Main benchmark (FALSE vs MISLEADING)
    bench = [e for e in examples if e.in_main_benchmark]
    main_benchmark = {
        "total":      len(bench),
        "FALSE":      sum(1 for e in bench if e.label_fine == "FALSE"),
        "MISLEADING": sum(1 for e in bench if e.label_fine == "MISLEADING"),
    }

    # Annotator notes stats
    flagged = sum(1 for e in examples if e.annotator_notes)

    stats = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_examples": len(examples) - label_dist.get(-1, 0),   # exported rows
        # every article seen once: exported rows + rows left out (excluded.csv)
        "total_including_unknown": len(examples) - label_dist.get(-1, 0) + len(exclusions),
        "excluded": dict(sorted(excluded.items(), key=lambda x: -x[1])),
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
            "total_without_date": len(examples) - len(dates),
        },
        "label_source_distribution": {
            source: {
                "count": count,
                "pct": f"{count/total*100:.1f}%"
            }
            for source, count in sorted(
                label_source_dist.items(), key=lambda x: -x[1]
            )
        },
        "label_fine_distribution": {
            label: {
                "count": count,
                "pct": f"{count/total*100:.1f}%"
            }
            for label, count in sorted(fine_dist.items(), key=lambda x: -x[1])
        },
        "label_fine_by_source": {
            source: dict(sorted(counts.items(), key=lambda x: -x[1]))
            for source, counts in sorted(fine_by_source.items())
        },
        "main_benchmark": main_benchmark,
        "claim_source_distribution": _dist("claim_source"),
        "language_distribution": _dist("language"),
        "date_precision_distribution": _dist("date_precision"),
        "split_distribution": _dist("split"),
        "split_random_distribution": _dist("split_random"),
        "language": {
            "nepali_script": nepali_count,
            "nepali_pct": f"{nepali_count/total*100:.1f}%",
        },
        "quality": {
            "flagged_for_review": flagged,
            "flagged_pct": f"{flagged/total*100:.1f}%",
        },
        "schema_version": SCHEMA_VERSION,   # was hardcoded "1.0"
    }

    return stats