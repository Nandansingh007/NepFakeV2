# pipeline/reference_labels.py
# =============================================================================
# Hand-checked reference labels (brief: reference-label test, M1 stored rows).
#
# File: data_validation/reference_labels.csv, keyed by source_url (IDs used
# to change; URLs do not). Columns (the blind hand-check sheet's columns are
# accepted as they are):
#     source_url  (or url)
#     label       (or YOUR_LABEL)  FALSE / MISLEADING / TRUE / UNVERIFIED /
#                                  BOTH / NOT_A_FACTCHECK
#     note        (optional)
#
# The file does not exist until you finish the hand check. While it is
# missing, nothing changes and the reference tests skip.
#
# When it exists, the normalizer uses it as an override:
#     FALSE / MISLEADING / TRUE / UNVERIFIED -> that label, label_source "hand_checked"
#     BOTH                                   -> MIXED,      label_source "hand_checked"
#     NOT_A_FACTCHECK                        -> row excluded, reason "hand_checked_not_factcheck"
# Rows with an empty label are ignored (sheet not finished).
# =============================================================================

import csv
from pathlib import Path

from config.settings import BASE_DIR
from utils.helpers import canonical_url

REFERENCE_FILE = BASE_DIR / "data_validation" / "reference_labels.csv"

ALLOWED = {"FALSE", "MISLEADING", "TRUE", "UNVERIFIED", "BOTH", "NOT_A_FACTCHECK"}


def load_reference_labels(path: Path = None) -> dict:
    """{canonical_url: label}. Empty dict if the file does not exist."""
    path = Path(path or REFERENCE_FILE)
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("source_url") or row.get("url") or "").strip()
            label = (row.get("label") or row.get("YOUR_LABEL") or "").strip().upper()
            if not url or not label:
                continue
            if label not in ALLOWED:
                raise ValueError(f"{path}: unknown label '{label}' for {url} "
                                 f"(allowed: {sorted(ALLOWED)})")
            out[canonical_url(url)] = label
    return out


def fine_label(reference: str) -> str:
    """Reference label -> label_fine ("" for NOT_A_FACTCHECK)."""
    return {"BOTH": "MIXED", "NOT_A_FACTCHECK": ""}.get(reference, reference)
