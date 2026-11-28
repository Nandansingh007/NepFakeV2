# pipeline/deduplicator.py
# =============================================================================
# Deduplication for NepFakeV2 normalized examples.
#
# Within a source, the same article (same canonical URL) can appear in several
# raw snapshots: the weekly incremental files, and the Phase 2 full re-scrape.
# The NEWEST snapshot wins (largest date_scraped; ties: the one read last).
# Until v2.0 the OLDEST copy won, which would have thrown a re-scrape away.
#
# Every replacement is recorded in LAST_REPORT, including rows whose fine
# label changed between snapshots. A test fails if too many labels change,
# because that usually means the scraper broke, not the fact-checker.
#
# Cross-source duplicates (the same claim checked by both fact-checkers) are
# NOT dropped; they are marked with claim_group_id (pipeline/claim_groups.py).
#
# Usage:
#   from pipeline.deduplicator import deduplicate
# =============================================================================

import logging

from schema.schema import NepFakeV2Example
from utils.helpers import canonical_url

logger = logging.getLogger("nepfakev2.deduplicator")

# Filled by every deduplicate() call
LAST_REPORT: dict = {"before": 0, "after": 0, "replaced": 0, "label_changed": []}


def deduplicate(examples: list[NepFakeV2Example]) -> list[NepFakeV2Example]:
    """
    Keep one record per (source_name, canonical URL): the newest snapshot.

    Output keeps the input order of the records that survive.
    """
    best: dict = {}        # key -> (rank, index, example)
    replaced, label_changed = 0, []

    for index, example in enumerate(examples):
        key = (example.source_name, canonical_url(example.source_url))
        rank = (example.date_scraped or "", index)
        if key not in best:
            best[key] = (rank, index, example)
            continue
        replaced += 1
        old_rank, _, old = best[key]
        newer, older = (example, old) if rank > old_rank else (old, example)
        if newer.label_fine != older.label_fine:
            label_changed.append({
                "source_url": newer.source_url,
                "old": older.label_fine, "new": newer.label_fine,
                "old_scraped": older.date_scraped, "new_scraped": newer.date_scraped,
            })
        if rank > old_rank:
            best[key] = (rank, index, example)

    kept = [e for _, _, e in sorted(best.values(), key=lambda t: t[1])]

    LAST_REPORT.clear()
    LAST_REPORT.update({
        "before": len(examples), "after": len(kept),
        "replaced": replaced, "label_changed": label_changed,
    })
    logger.info(
        f"Dedup: {replaced} older snapshots replaced, {len(kept)} kept, "
        f"{len(label_changed)} label changes between snapshots"
    )
    for change in label_changed[:20]:
        logger.warning(f"Label changed between snapshots: {change}")
    return kept


def get_dedup_stats(
    before: list[NepFakeV2Example],
    after: list[NepFakeV2Example],
) -> dict:
    """Deduplication statistics (kept for the collector's log line)."""
    return {
        "before": len(before),
        "after":  len(after),
        "removed": len(before) - len(after),
        "removal_rate": f"{(len(before)-len(after))/len(before)*100:.1f}%"
                        if before else "0%",
    }
