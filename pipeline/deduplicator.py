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
# Quality guard (Nov 2026, before the Phase 2 re-scrape): a newer snapshot
# does NOT replace an older one when it is clearly worse, because then the
# scraper failed on that page, not the article changed. "Worse" is any of:
#   - the label comes from a weaker place (LABEL_SOURCE_RANK below), e.g.
#     TechPana's conclusion box was read before and only the badge now
#   - the claim came from the fact-checker's own text before (claim box,
#     question headline, caption) and from a fallback now
#   - the article text (evidence + conclusion) is less than half as long
#
# One rule for every article with two snapshots (no person in the loop):
#   1. newer copy not degraded              -> newer copy
#   2. newer degraded, same label           -> older copy (the complete one)
#   3. newer degraded, labels differ        -> the copy whose label comes from
#      stronger evidence (LABEL_SOURCE_RANK); equal strength -> newer copy
# The chosen copy is used WHOLE (label, claim, evidence, dates): fields are
# never mixed between snapshots. A kept row whose label differs from another
# snapshot's (rule 1 or 3) gets snapshot_conflict = True and that label in
# snapshot_other_label. It stays in the dataset as silver; it leaves the
# benchmark only through the usual rule (badge-only "stored" labels are not
# in the benchmark). Every case is in LAST_REPORT and
# logs/snapshot_report.json. Conflicts never fail the run; the degraded-share
# gate in tests/test_identity_and_snapshots.py does.
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
LAST_REPORT: dict = {"before": 0, "after": 0, "replaced": 0, "label_changed": [],
                     "kept_older": [], "conflicts": [], "rescraped": {}}

# Higher = read from a better place in the article (config LABEL_SOURCES).
# A hand-checked label is the same in every snapshot, so it never degrades.
LABEL_SOURCE_RANK = {"hand_checked": 3, "nfc_header": 2, "conclusion": 2,
                     "conclusion_claim": 2, "conclusion_mixed": 2, "summary": 1, "stored": 0}

# claim_source values that are the fact-checker's own statement of the claim
GOOD_CLAIM_SOURCES = {"hand_checked", "claim_box", "headline_question", "claim_caption"}

# Text shorter than this before is too short to judge a drop by
MIN_TEXT_FOR_SHRINK = 300


def degradation(newer: NepFakeV2Example, older: NepFakeV2Example) -> list[str]:
    """Reasons why `newer` is a worse copy of the same article than `older`
    (empty list: newer is fine and replaces older)."""
    reasons = []
    if (LABEL_SOURCE_RANK.get(newer.label_source, 0)
            < LABEL_SOURCE_RANK.get(older.label_source, 0)):
        reasons.append(f"label_source {older.label_source} -> {newer.label_source}")
    if older.claim_source in GOOD_CLAIM_SOURCES and newer.claim_source not in GOOD_CLAIM_SOURCES:
        reasons.append(f"claim_source {older.claim_source} -> {newer.claim_source}")
    old_len = len(older.evidence_text or "") + len(older.conclusion_text or "")
    new_len = len(newer.evidence_text or "") + len(newer.conclusion_text or "")
    if old_len >= MIN_TEXT_FOR_SHRINK and new_len < 0.5 * old_len:
        reasons.append(f"text {old_len} -> {new_len} chars")
    return reasons


def deduplicate(examples: list[NepFakeV2Example]) -> list[NepFakeV2Example]:
    """
    Keep one record per (source_name, canonical URL): the newest snapshot,
    unless it is a degraded copy of an older one (see degradation()).

    Output keeps the input order of the records that survive.
    """
    best: dict = {}        # key -> (rank, index, example)
    replaced, label_changed, kept_older, conflicts = 0, [], [], []
    rescraped: dict = {}   # source_name -> number of URLs seen more than once
    other_labels: dict = {}  # key -> labels of snapshots that were not kept

    for example in examples:              # same result when called twice
        example.snapshot_conflict, example.snapshot_other_label = False, ""

    for index, example in enumerate(examples):
        key = (example.source_name, canonical_url(example.source_url))
        rank = (example.date_scraped or "", index)
        if key not in best:
            best[key] = (rank, index, example)
            continue
        old_rank, old_index, old = best[key]
        newer, older = (example, old) if rank > old_rank else (old, example)
        new_entry = (rank, index, example) if newer is example else (old_rank, old_index, old)
        old_entry = (old_rank, old_index, old) if newer is example else (rank, index, example)
        reasons = degradation(newer, older)
        same_label = newer.label_fine == older.label_fine
        case = {"source_name": newer.source_name, "source_url": newer.source_url,
                "old_scraped": older.date_scraped, "new_scraped": newer.date_scraped,
                "old_label": older.label_fine, "new_label": newer.label_fine,
                "old_label_source": older.label_source, "new_label_source": newer.label_source}
        if not reasons:                                         # rule 1
            winner, loser = new_entry, old_entry
            replaced += 1
            if not same_label:
                label_changed.append({
                    "source_url": newer.source_url,
                    "old": older.label_fine, "new": newer.label_fine,
                    "old_scraped": older.date_scraped, "new_scraped": newer.date_scraped,
                })
                conflicts.append({**case, "kept": "newer", "rule": "newer copy not degraded"})
        elif same_label:                                        # rule 2
            winner, loser = old_entry, new_entry
            kept_older.append({**case, "reasons": reasons})
        else:                                                   # rule 3
            stronger_new = (LABEL_SOURCE_RANK.get(newer.label_source, 0)
                            >= LABEL_SOURCE_RANK.get(older.label_source, 0))
            winner, loser = (new_entry, old_entry) if stronger_new else (old_entry, new_entry)
            if not stronger_new:
                kept_older.append({**case, "reasons": reasons})
            conflicts.append({**case, "kept": "newer" if stronger_new else "older",
                              "reasons": reasons,
                              "rule": "degraded copy, stronger label source wins"
                                      + (" (equal: newer)" if stronger_new else "")})
        if not same_label:
            other_labels.setdefault(key, []).append(loser[2].label_fine)
        rescraped.setdefault(example.source_name, set()).add(key)
        # a third snapshot is compared with the copy that is actually kept
        best[key] = winner

    for key, labels in other_labels.items():
        kept_example = best[key][2]
        others = sorted({l for l in labels if l != kept_example.label_fine})
        if others:
            kept_example.snapshot_conflict = True
            kept_example.snapshot_other_label = "|".join(others)

    kept = [e for _, _, e in sorted(best.values(), key=lambda t: t[1])]

    LAST_REPORT.clear()
    LAST_REPORT.update({
        "before": len(examples), "after": len(kept),
        "replaced": replaced, "label_changed": label_changed,
        "kept_older": kept_older, "conflicts": conflicts,
        "rescraped": {s: len(keys) for s, keys in sorted(rescraped.items())},
    })
    logger.info(
        f"Dedup: {replaced} older snapshots replaced, {len(kept_older)} newer "
        f"snapshots refused as degraded, {len(kept)} kept, "
        f"{len(label_changed)} label changes between snapshots"
    )
    for change in label_changed[:20]:
        logger.warning(f"Label changed between snapshots: {change}")
    for case in kept_older[:20]:
        logger.warning(f"Newer snapshot degraded, older kept: {case}")
    for case in conflicts[:20]:
        logger.warning(f"Snapshots disagree on the label, kept the {case['kept']} copy: {case}")
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
