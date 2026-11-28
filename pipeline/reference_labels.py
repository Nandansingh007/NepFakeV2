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


# =============================================================================
# Sheet of rows whose label a person must read: python -m pipeline.reference_labels sheet
# =============================================================================
# Lists every Nepali row whose label was NOT read from the article text
# (label_source "stored"): TechPana rows labelled only by the og:image badge
# (files before 12 Oct 2026 may hold a sidebar badge, and the 28 Nov 2026
# re-scrape no longer found the badge on 27 of them), and NepalFactCheck
# rows without one clear header tag (e.g. a page tagged both अपुष्ट and
# भ्रामक). These rows are outside the benchmark until a person checks them.
#
# Writes data_validation/labels_to_check.csv (git-ignored). Fill `label`
# (FALSE / MISLEADING / TRUE / UNVERIFIED / BOTH / NOT_A_FACTCHECK), then add
# the rows to data_validation/reference_labels.csv (save as CSV UTF-8).

LABEL_SHEET_FILE = BASE_DIR / "data_validation" / "labels_to_check.csv"
LABEL_SHEET_COLUMNS = ["source_url", "label", "note", "source_name", "headline",
                       "current_label", "label_source", "badge_url", "why", "conclusion"]
NEEDS_PERSON = {"stored"}


def write_label_sheet(path: Path = None) -> int:
    """Write the label sheet. Returns the number of rows."""
    from pipeline.normalizer import load_raw, normalize_article
    from pipeline.text_rules import devanagari_share
    from scrapers.techpana import conclusion_text_for_sheet

    path = Path(path or LABEL_SHEET_FILE)
    done = load_reference_labels()
    raws = {}
    for raw in load_raw():
        raws[canonical_url(raw.get("source_url", ""))] = raw     # newest snapshot last
    rows = []
    for key, raw in raws.items():
        excluded = []
        ex = normalize_article(raw, {}, excluded)                # the rule's label
        title = raw.get("title") or ""
        if ex is None:
            # newest scrape found no verdict at all: a person must read it
            if not (excluded and excluded[0]["reason"] == "verdict_unmappable"
                    and devanagari_share(title) >= 0.5):
                continue
            current, label_source = "", "none"
            why = "no verdict found on the page (newest scrape)"
        elif ex.label_source in NEEDS_PERSON and ex.language == "ne":
            current, label_source = ex.label_fine, ex.label_source
            why = ("badge only (no verdict in the conclusion or summary)"
                   if ex.source_name == "techpana"
                   else "no single header tag (none, or several)")
        else:
            continue
        rows.append({
            "source_url": raw.get("source_url", ""),
            "label": done.get(key, ""),
            "note": "",
            "source_name": raw.get("source_name", ""),
            "headline": title,
            "current_label": current,
            "label_source": label_source,
            "badge_url": raw.get("badge_url", ""),
            "why": why,
            "conclusion": conclusion_text_for_sheet(raw.get("body_text") or "")[:500],
        })
    rows.sort(key=lambda r: (r["source_name"], r["source_url"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LABEL_SHEET_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main(argv=None) -> int:
    import logging
    import sys
    logging.basicConfig(level=logging.ERROR)       # the rule's warnings are the point of the sheet
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["sheet"]:
        print("usage: python -m pipeline.reference_labels sheet")
        return 2
    n = write_label_sheet()
    print(f"wrote {LABEL_SHEET_FILE.relative_to(BASE_DIR)}: {n} rows whose label a person "
          f"must read ({len(load_reference_labels())} labels already in reference_labels.csv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
