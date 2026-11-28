# pipeline/label_mapper.py
# =============================================================================
# Maps raw verdict text from all sources to NepFakeV2 label integers.
#
# Sources:
#   TechPana       — Nepali verdict keywords
#   NepalFactCheck — Nepali verdict keywords with सूचना suffix
#
# Labels:
#   0 = REAL
#   1 = FALSE_MISLEADING
#   2 = UNVERIFIED
#  -1 = UNKNOWN (could not map — flagged for manual review)
#
# Usage:
#   from pipeline.label_mapper import map_verdict, LABEL_NAMES
# =============================================================================


# =============================================================================
# LABEL DEFINITIONS
# =============================================================================

LABEL_NAMES = {
    0:  "REAL",
    1:  "FALSE_MISLEADING",
    2:  "UNVERIFIED",
    -1: "UNKNOWN",
}

# =============================================================================
# VERDICT MAPPING
# Raw verdict strings from all active sources → label integer
# Order matters — more specific matches first
# =============================================================================

VERDICT_MAP = {
    # --- NepalFactCheck verdicts (with सूचना suffix) ---
    # Check these first — more specific than short forms
    "मिथ्या सूचना":  1,   # False information
    "भ्रामक सूचना":  1,   # Misleading information
    "अपुष्ट सूचना":  2,   # Unverified information
    "सही सूचना":     0,   # True information

    # --- TechPana standard verdicts ---
    "मिथ्या":        1,   # False
    "भ्रामक":        1,   # Misleading
    "अपुष्ट":        2,   # Unverified
    "सही":           0,   # True

    # --- TechPana informal variants ---
    "झुटो":          1,   # Informal "false"
    "गलत":           1,   # "Wrong"
    "असत्य":         1,   # Formal "untrue"
    "भ्रम":          1,   # "Confusion/misleading"
    "साँचो":         0,   # Informal "true"
    "सत्य":          0,   # Formal "true"
}


# Fine labels (schema 2.0): same keys, same order as VERDICT_MAP, so the
# fine and the coarse label always agree (tested in test_label_fine.py)
VERDICT_MAP_FINE = {
    "मिथ्या सूचना":  "FALSE",
    "भ्रामक सूचना":  "MISLEADING",
    "अपुष्ट सूचना":  "UNVERIFIED",
    "सही सूचना":     "TRUE",
    "मिथ्या":        "FALSE",
    "भ्रामक":        "MISLEADING",
    "अपुष्ट":        "UNVERIFIED",
    "सही":           "TRUE",
    "झुटो":          "FALSE",
    "गलत":           "MISLEADING",   # decided Nov 2026 ("wrong context")
    "असत्य":         "FALSE",
    "भ्रम":          "MISLEADING",
    "साँचो":         "TRUE",
    "सत्य":          "TRUE",
}


# =============================================================================
# MAPPING FUNCTIONS
# =============================================================================

# A "true" word followed by a negation is not a verdict ("सही होइन")
_NEGATION = r"\s*(?:होइन|हैन|छैन|नभएको|देखिँदैन|देखिदैन)"
_DEV = "\u0900-\u097F"


def _fine_matches(cleaned: str) -> set:
    """Fine labels named in the text: whole words only, negated TRUE words
    ignored. ("भ्रम" must not match "भ्रमण"; "सही होइन" is not TRUE.)"""
    import re
    found = set()
    for keyword, fine in VERDICT_MAP_FINE.items():
        for m in re.finditer(rf"(?<![{_DEV}]){re.escape(keyword)}(?![{_DEV}])", cleaned):
            if fine == "TRUE" and re.match(_NEGATION, cleaned[m.end():]):
                continue
            found.add(fine)
    return found


def map_verdict(raw_verdict_text: str) -> tuple[int, str]:
    """
    Map raw verdict text to the coarse label (int, text).

    Since 2.0 the coarse label is DERIVED from the fine label
    (map_verdict_fine + LABEL_FINE_TO_COARSE), so the two can never
    disagree. -1 UNKNOWN when no verdict, or two different verdicts, are
    named.
    """
    from config.settings import LABEL_FINE_TO_COARSE
    fine = map_verdict_fine(raw_verdict_text)
    if not fine:
        return -1, "UNKNOWN"
    label = LABEL_FINE_TO_COARSE[fine]
    return label, LABEL_NAMES[label]


def map_verdict_label(raw_verdict_text: str) -> int:
    """
    Returns only the label integer.
    Convenience wrapper around map_verdict().
    """
    label, _ = map_verdict(raw_verdict_text)
    return label


def map_verdict_text(raw_verdict_text: str) -> str:
    """
    Returns only the label text string.
    Convenience wrapper around map_verdict().
    """
    _, label_text = map_verdict(raw_verdict_text)
    return label_text


def is_mappable(raw_verdict_text: str) -> bool:
    """
    Returns True if verdict can be mapped to a valid label.
    Returns False for empty or unknown verdicts.
    """
    label, _ = map_verdict(raw_verdict_text)
    return label != -1


def get_label_distribution(verdicts: list[str]) -> dict:
    """
    Get label distribution from a list of raw verdict strings.
    Useful for quality checking raw data.

    Args:
        verdicts: List of raw verdict strings

    Returns:
        Dict with label counts and percentages
    """
    counts = {0: 0, 1: 0, 2: 0, -1: 0}
    for v in verdicts:
        label, _ = map_verdict(v)
        counts[label] = counts.get(label, 0) + 1

    total = len(verdicts)
    return {
        LABEL_NAMES[label]: {
            "count": count,
            "pct": f"{count/total*100:.1f}%" if total > 0 else "0%"
        }
        for label, count in counts.items()
    }

def map_verdict_fine(raw_verdict_text: str) -> str:
    """
    Map raw verdict text to the fine label (schema 2.0):
    "FALSE" / "MISLEADING" / "TRUE" / "UNVERIFIED", or "" if not mappable.

    1. exact match against VERDICT_MAP_FINE
    2. otherwise the fine labels named as whole words (negated TRUE words
       ignored): exactly one -> that label; none or several -> "" (brief
       B2: before 2.0 the first partial match won, so "सही होइन, भ्रामक"
       came out TRUE).

    There is no MIXED label (removed 28 Nov 2026): a TechPana conclusion
    naming both is resolved in scrapers/techpana.py resolve_verdict.
    """
    if not raw_verdict_text or not raw_verdict_text.strip():
        return ""
    cleaned = raw_verdict_text.strip()
    if cleaned in VERDICT_MAP_FINE:
        return VERDICT_MAP_FINE[cleaned]
    found = _fine_matches(cleaned)
    return found.pop() if len(found) == 1 else ""
