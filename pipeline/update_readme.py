# pipeline/update_readme.py
# =============================================================================
# Injects live dataset statistics into README.md after every pipeline run.
# Reads data/stats.json and raw/stats_raw.json and rewrites the block
# between <!-- STATS_START --> and <!-- STATS_END --> markers.
#
# Usage:
#   from pipeline.update_readme import update_readme_stats
#   Called automatically by collector.py after export.
# =============================================================================

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config.settings import DATA_DIR, RAW_DIR, BASE_DIR

logger = logging.getLogger("nepfakev2.update_readme")

README_PATH = BASE_DIR / "README.md"
STATS_START = "<!-- STATS_START -->"
STATS_END   = "<!-- STATS_END -->"

# Maps raw Nepali verdict text to short display label
VERDICT_DISPLAY = {
    # TechPana
    "भ्रामक":        "भ्रामक",
    "मिथ्या":        "मिथ्या",
    "अपुष्ट":        "अपुष्ट",
    "सही":           "सही",
    # NepalFactCheck
    "भ्रामक सूचना":  "भ्रामक",
    "मिथ्या सूचना":  "मिथ्या",
    "अपुष्ट सूचना":  "अपुष्ट",
    "सही सूचना":     "सही",
    "EMPTY":         "unmapped",
}

LABEL_ORDER = ["REAL", "FALSE_MISLEADING", "UNVERIFIED", "UNKNOWN"]

SOURCE_DISPLAY = {
    "techpana":       "TechPana",
    "nepalfactcheck": "NepalFactCheck",
}


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_source_verdict_breakdown(raw_by_source: dict) -> str:
    """
    Build per-source verdict breakdown line.
    e.g. TechPana  264 examples | भ्रामक: 72%  मिथ्या: 22%  अपुष्ट: 3%  सही: 1%  unmapped: 3%
    """
    lines = []
    for source_key, display_name in SOURCE_DISPLAY.items():
        source_data = raw_by_source.get(source_key, {})
        total = source_data.get("total", 0)
        if not total:
            continue

        verdict_dist = source_data.get("verdict_distribution", {})
        empty = source_data.get("empty_verdicts", 0)

        # Aggregate into display buckets
        buckets: dict[str, int] = {}
        for raw_verdict, count in verdict_dist.items():
            display = VERDICT_DISPLAY.get(raw_verdict.strip(), "other")
            buckets[display] = buckets.get(display, 0) + count

        # Sort by count descending
        sorted_buckets = sorted(buckets.items(), key=lambda x: -x[1])

        verdict_str = "  ".join(
            f"{label}: {count/total*100:.0f}%"
            for label, count in sorted_buckets
            if count > 0
        )

        # Flag unmapped if any
        unmapped_note = f"  ⚠ {empty} unmapped" if empty > 0 else ""

        lines.append(
            f"| {display_name:<16} | {total:>4} | {verdict_str}{unmapped_note} |"
        )

    return "\n".join(lines)


def build_stats_block(stats: dict, raw_stats: dict) -> str:
    """Build the markdown stats block to inject into README.md."""

    # Timestamp
    last_updated = stats.get("last_updated", "")
    try:
        dt = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        updated_str = dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        updated_str = last_updated[:10] if last_updated else "unknown"

    total_examples        = stats.get("total_examples", 0)
    total_including_unknown = stats.get("total_including_unknown", total_examples)
    unknown_count         = total_including_unknown - total_examples
    label_dist            = stats.get("label_distribution", {})
    date_range            = stats.get("date_range", {})
    language              = stats.get("language", {})
    raw_by_source         = raw_stats.get("by_source", {})

    oldest = date_range.get("oldest", "N/A")
    newest = date_range.get("newest", "N/A")

    # Label distribution rows — always show UNKNOWN even if 0
    label_rows = ""
    for label in LABEL_ORDER:
        if label in label_dist:
            d = label_dist[label]
            label_rows += f"| {label:<20} | {d['count']:>5} | {d['pct']:>6} |\n"

    # Always show UNKNOWN row — even if 0 — so researchers know it exists
    if "UNKNOWN" not in label_dist:
        label_rows += f"| {'UNKNOWN':<20} | {0:>5} | {'0.0%':>6} |\n"

    # Source verdict breakdown
    source_breakdown = format_source_verdict_breakdown(raw_by_source)

    # Unmapped note
    unmapped_note = ""
    if unknown_count > 0:
        unmapped_note = (
            f"\n> ⚠ **{unknown_count} unmapped records** excluded from dataset "
            f"— verdict text could not be mapped to a label. "
            f"See `annotator_notes` field in raw data.\n"
        )

    block = f"""\
<!-- STATS_START -->
## Dataset Statistics

**{total_examples} examples** &nbsp;|&nbsp; {oldest} → {newest} &nbsp;|&nbsp; Updated: {updated_str}
{unmapped_note}
### Label Distribution

| Label | Count | % |
|-------|------:|--:|
{label_rows}
### Source Breakdown

| Source | Examples | Verdict profile |
|--------|----------:|-----------------|
{source_breakdown}

Nepali script coverage: **{language.get('nepali_pct', 'N/A')}**
<!-- STATS_END -->"""

    return block


def update_readme_stats() -> bool:
    """
    Inject live stats into README.md between placeholder comments.

    Returns:
        True if README was updated, False if markers not found or error.
    """
    if not README_PATH.exists():
        logger.warning(f"README.md not found at {README_PATH}")
        return False

    stats     = load_json(DATA_DIR / "stats.json")
    raw_stats = load_json(RAW_DIR  / "stats_raw.json")

    if not stats:
        logger.warning("stats.json empty or missing — skipping README update")
        return False

    content = README_PATH.read_text(encoding="utf-8")

    start_idx = content.find(STATS_START)
    end_idx   = content.find(STATS_END)

    if start_idx == -1 or end_idx == -1:
        logger.warning(
            "README.md missing <!-- STATS_START --> or <!-- STATS_END --> "
            "markers — skipping stats injection"
        )
        return False

    new_block = build_stats_block(stats, raw_stats)
    new_content = (
        content[:start_idx] +
        new_block +
        content[end_idx + len(STATS_END):]
    )

    README_PATH.write_text(new_content, encoding="utf-8")
    logger.info("README.md stats block updated")
    return True