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


# =============================================================================
# MAPPING FUNCTIONS
# =============================================================================

def map_verdict(raw_verdict_text: str) -> tuple[int, str]:
    """
    Map raw verdict text to NepFakeV2 label integer and text.

    Strategy:
        1. Exact match against VERDICT_MAP
        2. Partial match — check if any keyword is in verdict text
        3. Return -1 UNKNOWN if no match found

    Args:
        raw_verdict_text: Raw verdict string from scraper
                          e.g. "भ्रामक" / "भ्रामक सूचना" / ""

    Returns:
        Tuple of (label_int, label_text)
        e.g. (1, "FALSE_MISLEADING")
             (-1, "UNKNOWN") if not mappable
    """
    if not raw_verdict_text or not raw_verdict_text.strip():
        return -1, "UNKNOWN"

    cleaned = raw_verdict_text.strip()

    # Strategy 1: exact match
    if cleaned in VERDICT_MAP:
        label = VERDICT_MAP[cleaned]
        return label, LABEL_NAMES[label]

    # Strategy 2: partial match
    # Handles variants like "दाबी भ्रामक छ" or "यो मिथ्या हो"
    for keyword, label in VERDICT_MAP.items():
        if keyword in cleaned:
            return label, LABEL_NAMES[label]

    return -1, "UNKNOWN"


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