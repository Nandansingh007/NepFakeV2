# pipeline/claims_reference.py
# =============================================================================
# Hand-checked claims (the claim_text hand pass).
#
# Two files in data_validation/:
#
#   claims_to_check.csv   the draft sheet. Written by
#                             python -m pipeline.claims_reference sheet
#                         One row per benchmark article whose claim did not
#                         come from NFC's claim box or a "के … हो?" headline
#                         (all TechPana rows, NFC rows mostly from 2020).
#                         claim_text is pre-filled with the rule's draft.
#
#   claims_reference.csv  the same sheet after you checked it (save a copy
#                         under this name). Read by the normalizer.
#
# Columns used (the sheet's other columns are context and are ignored):
#     source_url   the key (IDs used to change; URLs do not)
#     claim_text   the claim as a person would state it, without the verdict
#     claimant     who made it (optional)
#     claim_platform  where it spread (optional): facebook, tiktok, x,
#                  youtube, instagram, messaging, news_media; several with |
#     checked      y once you have read the article and the claim is right
#     note         optional
#
# Only rows with checked = y are used: an unchecked draft never overrides the
# rules. A used row sets claim_source "hand_checked". A claim_text that
# contains a verdict word (मिथ्या, भ्रामक, …) is refused with an error, so a
# hand-written claim can never leak the label.
#
# While claims_reference.csv does not exist, nothing changes.
# =============================================================================

import csv
import sys
from pathlib import Path

from config.settings import BASE_DIR
from pipeline.claim_extractor import PLATFORM_VALUES
from pipeline.text_rules import leaks_verdict
from utils.helpers import canonical_url

CLAIMS_FILE = BASE_DIR / "data_validation" / "claims_reference.csv"
SHEET_FILE = BASE_DIR / "data_validation" / "claims_to_check.csv"

# Rule sources that do not need a person (measured 28 Nov 2026: 0 of 30
# sampled NFC box claims were "not a claim")
TRUSTED_SOURCES = {"claim_box", "headline_question"}

SHEET_COLUMNS = ["source_url", "example_id", "source_name", "date_published",
                 "rule_source", "headline", "claim_section", "lead",
                 "claim_text", "claimant", "claim_platform", "checked", "note"]

YES = {"y", "yes", "1", "x", "true"}


def load_claims(path: Path = None) -> dict:
    """{canonical_url: {"claim_text", "claimant", "claim_platform"}} for checked rows.
    Empty dict if the file does not exist."""
    path = Path(path or CLAIMS_FILE)
    if not path.exists():
        return {}
    out = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("source_url") or "").strip()
            claim = " ".join((row.get("claim_text") or "").split())
            if not url or not claim or (row.get("checked") or "").strip().lower() not in YES:
                continue
            if len(claim) < 10:
                raise ValueError(f"{path}: claim_text too short for {url}: '{claim}'")
            if leaks_verdict(claim):
                raise ValueError(f"{path}: claim_text states the verdict for {url}: '{claim}' "
                                 f"(remove मिथ्या/भ्रामक/… : write the claim, not the finding)")
            platform = "|".join(p.strip().lower() for p in
                                (row.get("claim_platform") or "").replace(",", "|").split("|")
                                if p.strip())
            bad = [p for p in platform.split("|") if p and p not in PLATFORM_VALUES]
            if bad:
                raise ValueError(f"{path}: unknown claim_platform {bad} for {url} "
                                 f"(allowed: {', '.join(PLATFORM_VALUES)})")
            out[canonical_url(url)] = {
                "claim_text": claim,
                "claimant": " ".join((row.get("claimant") or "").split()),
                "claim_platform": "|".join(p for p in PLATFORM_VALUES if p in platform.split("|")),
            }
    return out


def write_sheet(path: Path = None) -> int:
    """Write the draft sheet for the hand pass. Returns the number of rows.
    Rows already checked in claims_reference.csv keep your text."""
    from pipeline.claim_extractor import tp_claim_section
    from pipeline.normalizer import load_raw, normalize_article
    from pipeline.reference_labels import load_reference_labels

    path = Path(path or SHEET_FILE)
    done = load_claims()
    references = load_reference_labels()
    raws = {}
    for raw in load_raw():
        raws[raw.get("source_url", "")] = raw          # newest snapshot last
    rows = []
    for url, raw in raws.items():
        ex = normalize_article(raw, references)        # rule claims, hand labels
        if ex is None or not ex.in_main_benchmark or ex.claim_source in TRUSTED_SOURCES:
            continue
        body = raw.get("body_text") or ""
        mine = done.get(canonical_url(url))
        rows.append({
            "source_url": url,
            "example_id": ex.example_id,
            "source_name": ex.source_name,
            "date_published": ex.date_published,
            "rule_source": ex.claim_source,
            "headline": ex.headline,
            "claim_section": tp_claim_section(body)[:700],
            "lead": " ".join(ex.evidence_text.split())[:500],
            "claim_text": mine["claim_text"] if mine else ex.claim_text,
            "claimant": mine["claimant"] if mine else ex.claimant,
            "claim_platform": mine["claim_platform"] if mine and mine["claim_platform"] else ex.claim_platform,
            "checked": "y" if mine else "",
            "note": "",
        })
    rows.sort(key=lambda r: (r["source_name"], r["date_published"], r["source_url"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig so Excel shows Devanagari; save back as "CSV UTF-8"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["sheet"]:
        print("usage: python -m pipeline.claims_reference sheet")
        return 2
    n = write_sheet()
    print(f"wrote {SHEET_FILE.relative_to(BASE_DIR)}: {n} rows to check "
          f"({len(load_claims())} already checked in claims_reference.csv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
