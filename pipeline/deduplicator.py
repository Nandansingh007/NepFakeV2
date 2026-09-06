# pipeline/deduplicator.py
# =============================================================================
# Deduplication for NepFakeV2 normalized examples.
#
# Strategy:
#   Level 1 — Within source: normalized URL match → DROP duplicate
#
# Cross-source deduplication is NOT attempted:
#   Requires Nepali NLP (Named Entity Recognition) to reliably detect
#   same claim across different fact-checkers with different wording.
#   Documented as known limitation in dataset paper.
#
# Usage:
#   from pipeline.deduplicator import deduplicate
# =============================================================================

import logging
from utils.helpers import normalize_url
from schema.schema import NepFakeV2Example

logger = logging.getLogger("nepfakev2.deduplicator")


def deduplicate(
    examples: list[NepFakeV2Example],
) -> list[NepFakeV2Example]:
    """
    Deduplicate NepFakeV2Example records within each source.

    Same article scraped multiple times (e.g. different query params)
    → keep first occurrence, drop rest.

    Cross-source duplicates (same claim fact-checked by multiple sources)
    → kept as-is. Documented limitation. Researchers can handle downstream.

    Args:
        examples: List of NepFakeV2Example to deduplicate

    Returns:
        Deduplicated list
    """
    seen_source_urls = {}  # (source_name, normalized_url) → example_id
    kept = []
    dropped = 0

    for example in examples:
        norm_url = normalize_url(example.source_url)
        key = (example.source_name, norm_url)

        if key in seen_source_urls:
            dropped += 1
            logger.debug(
                f"Duplicate dropped: {example.source_url} "
                f"(same as {seen_source_urls[key]})"
            )
        else:
            seen_source_urls[key] = example.example_id
            kept.append(example)

    logger.info(
        f"Dedup complete: {dropped} duplicates removed, "
        f"{len(kept)} records kept"
    )

    return kept


def get_dedup_stats(
    before: list[NepFakeV2Example],
    after: list[NepFakeV2Example],
) -> dict:
    """
    Get deduplication statistics.

    Args:
        before: Examples before deduplication
        after:  Examples after deduplication

    Returns:
        Dict with dedup stats
    """
    return {
        "before": len(before),
        "after":  len(after),
        "removed": len(before) - len(after),
        "removal_rate": f"{(len(before)-len(after))/len(before)*100:.1f}%"
                        if before else "0%",
    }