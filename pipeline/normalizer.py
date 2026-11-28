# pipeline/normalizer.py
# =============================================================================
# Normalizes raw scraped articles into NepFakeV2Example records (schema 2.0).
#
# Input:  raw/<source>/<date>.json (never edited)
# Output: NepFakeV2Example records, plus LAST_EXCLUSIONS (what was left out
#         and why; written to data/excluded.csv by the exporter)
#
# Per article:
#   - verdict: NFC header tag / TechPana conclusion -> summary -> stored
#   - hand-checked override (data_validation/reference_labels.csv), if any
#   - label_fine and in_main_benchmark
#   - claim_text (the claim, not the headline) and claim_source
#   - evidence_text (no verdict words) and conclusion_text
#   - stable example_id from the URL
#   - date_published, date_precision, date_scraped
#   - language, is_native_nepali, topic_category
#   - external_evidence_urls without share buttons and self-links
#
# Usage:
#   from pipeline.normalizer import normalize_article, normalize_all
# =============================================================================

import re
import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config.settings import (RAW_DIRS, SCHEMA_VERSION, BENCHMARK_EXCLUDED_SOURCES,
                             LABEL_FINE_TO_COARSE, LABELS)
from schema.schema import NepFakeV2Example, make_example_id
from schema.validator import validate_batch
from pipeline.label_mapper import map_verdict, map_verdict_fine
from pipeline.claim_extractor import extract_claim
from pipeline.evidence_cleaner import clean_evidence
from pipeline.reference_labels import load_reference_labels, fine_label
from pipeline.text_rules import devanagari_share
from scrapers.techpana import (BS_MONTHS, parse_bs_date, extract_own_date,
                               is_factcheck_article, resolve_verdict)
from scrapers.nepalfactcheck import extract_verdict_from_header, is_explainer
from utils.helpers import canonical_url

logger = logging.getLogger("nepfakev2.normalizer")

# Filled by normalize_all(): one dict per article that was left out
#   {"source_name", "source_url", "reason", "date_scraped"}
# Reasons: explainer, not_a_factcheck, verdict_unmappable, no_title_or_body,
#          hand_checked_not_factcheck, validation_failed
LAST_EXCLUSIONS: list[dict] = []


# =============================================================================
# DATE NORMALIZATION
# =============================================================================

def normalize_date_with_precision(raw_date: str) -> tuple[str, str]:
    """
    ("YYYY-MM-DD", precision). precision is "day", "month", "year" or "".

    A year-only date becomes YYYY-01-01 with precision "year", so a time
    split can tell it is not really 1 January (brief N9).
    """
    if not raw_date or not raw_date.strip():
        return "", ""
    raw_date = raw_date.strip()

    if raw_date[0].isdigit():
        if "T" in raw_date and re.match(r"^\d{4}-\d{2}-\d{2}T", raw_date):
            return raw_date[:10], "day"
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            return raw_date, "day"
        if re.match(r"^\d{4}-\d{2}$", raw_date):
            return f"{raw_date}-01", "month"
        if re.match(r"^\d{4}$", raw_date):
            return f"{raw_date}-01-01", "year"

    for month in BS_MONTHS.keys():
        if raw_date.startswith(month):
            converted = parse_bs_date(raw_date)
            if converted:
                return converted, "day"
            break

    logger.warning(f"Could not parse date: {raw_date}")
    return "", ""


def normalize_date(raw_date: str) -> str:
    """ISO date only (kept for callers and tests from before 2.0)."""
    return normalize_date_with_precision(raw_date)[0]


# =============================================================================
# TOPIC CATEGORY DETECTION (keyword heuristic; metadata only, see DATASHEET)
# =============================================================================

TOPIC_KEYWORDS = {
    "politics": [
        "सरकार", "संसद", "प्रधानमन्त्री", "राष्ट्रपति", "चुनाव",
        "निर्वाचन", "दल", "पार्टी", "नेता", "मन्त्री", "संविधान",
        "government", "parliament", "election", "minister", "political"
    ],
    "health": [
        "स्वास्थ्य", "अस्पताल", "खोप", "भाइरस", "कोभिड", "औषधि",
        "रोग", "उपचार", "डाक्टर", "hospital", "vaccine", "virus",
        "covid", "medicine", "disease", "health"
    ],
    "technology": [
        "प्रविधि", "इन्टरनेट", "सफ्टवेयर", "एआई", "डिजिटल",
        "technology", "internet", "software", "AI", "digital",
        "computer", "cyber", "deepfake", "एप"
    ],
    "society": [
        "समाज", "महिला", "बालबालिका", "शिक्षा", "धर्म", "संस्कृति",
        "समुदाय", "social", "women", "children", "education",
        "religion", "culture", "community"
    ],
    "environment": [
        "वातावरण", "बाढी", "भूकम्प", "मौसम", "जलवायु", "प्रकोप",
        "environment", "flood", "earthquake", "weather", "climate",
        "disaster", "landslide", "बाढी"
    ],
    "economy": [
        "अर्थतन्त्र", "बैंक", "रुपैयाँ", "बजेट", "व्यापार",
        "economy", "bank", "budget", "trade", "finance", "rupee"
    ],
}


def detect_topic(title: str, body_text: str) -> str:
    """Keyword match on the title and the first 500 characters."""
    search_text = (title + " " + body_text[:500]).lower()
    scores = {}
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in search_text)
        if score > 0:
            scores[topic] = score
    if not scores:
        return "other"
    return max(scores, key=scores.get)


# =============================================================================
# EXTERNAL LINKS
# =============================================================================

OWN_HOSTS = {"techpana.com", "nepalfactcheck.org"}
OWN_ACCOUNTS = ("techpana", "nepalfactcheck", "cmrnepal")
SHARE_PATTERNS = ("sharer", "/share?", "intent/tweet", "sharearticle", "/hashtag/",
                  "whatsapp://", "mailto:")
MAX_LINKS = 20


def filter_external_links(links: list, source_url: str) -> list[str]:
    """
    Drop the outlet's own pages and social accounts, share buttons and
    hashtag links; keep the order and at most MAX_LINKS. Before 2.0 the
    first 5 links were kept, which were mostly the outlet's own Facebook /
    Twitter / LinkedIn buttons.
    """
    out, seen = [], set()
    for link in links or []:
        if not isinstance(link, str) or not link.startswith("http"):
            continue
        host = urlparse(link).netloc.lower().removeprefix("www.")
        low = link.lower()
        if host in OWN_HOSTS or host.endswith(tuple("." + h for h in OWN_HOSTS)):
            continue
        if any(p in low for p in SHARE_PATTERNS):
            continue
        segments = [x.lstrip("@") for x in urlparse(low).path.strip("/").split("/")[:2]]
        if any(acc in seg for acc in OWN_ACCOUNTS for seg in segments):
            continue                     # the outlet's own social account
                                         # (facebook.com/TechPanaNews, linkedin.com/in/cmrnepal)
        key = low.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
        if len(out) >= MAX_LINKS:
            break
    return out


# =============================================================================
# NORMALIZER
# =============================================================================

def _exclude(exclusions, raw, reason):
    if exclusions is not None:
        exclusions.append({
            "source_name": raw.get("source_name", ""),
            "source_url": raw.get("source_url", ""),
            "reason": reason,
            "date_scraped": raw.get("date_scraped", ""),
        })
    return None


def normalize_article(raw: dict, references: Optional[dict] = None,
                      exclusions: Optional[list] = None) -> Optional[NepFakeV2Example]:
    """
    Normalize one raw article. Returns None when the article is left out;
    the reason is appended to `exclusions` (if given).

    Args:
        raw:        raw article dict from raw/<source>/<date>.json
        references: {canonical_url: hand-checked label} (see reference_labels)
        exclusions: list that collects the reason for each left-out article
    """
    references = references or {}
    source_name = raw.get("source_name", "")
    source_url = raw.get("source_url", "")
    title = (raw.get("title") or "").strip()
    body_text = (raw.get("body_text") or "").strip()
    raw_verdict = (raw.get("raw_verdict_text") or "").strip()
    raw_date = raw.get("date_published", "")
    annotator_notes = raw.get("annotator_notes", "") or ""

    if not title or not body_text:
        logger.warning(f"Skipping, no title or body: {source_url}")
        return _exclude(exclusions, raw, "no_title_or_body")

    # --- Verdict (raw files unchanged; re-derived from the saved text) ---
    label_source = "stored"
    if source_name == "nepalfactcheck":
        if is_explainer(body_text, title):
            return _exclude(exclusions, raw, "explainer")
        header_verdict = extract_verdict_from_header(body_text, title)
        if header_verdict:
            raw_verdict, label_source = header_verdict, "nfc_header"
    elif source_name == "techpana":
        if not is_factcheck_article(title, body_text, source_url):
            return _exclude(exclusions, raw, "not_a_factcheck")
        raw_date = extract_own_date(body_text) or raw_date
        raw_verdict, label_source = resolve_verdict(body_text, raw_verdict)

    verdict_label, verdict_label_text = map_verdict(raw_verdict)
    if verdict_label == -1:
        label_fine = ""
    elif label_source == "conclusion_mixed":
        label_fine = "MIXED"
    else:
        label_fine = map_verdict_fine(raw_verdict)

    # --- Hand-checked override (only once the reference file exists) ---
    reference = references.get(canonical_url(source_url))
    if reference == "NOT_A_FACTCHECK":
        return _exclude(exclusions, raw, "hand_checked_not_factcheck")
    if reference:
        label_fine = fine_label(reference)
        verdict_label = LABEL_FINE_TO_COARSE[label_fine]
        verdict_label_text = LABELS[verdict_label]
        label_source = "hand_checked"

    if verdict_label == -1:
        logger.warning(f"Unmappable verdict '{raw_verdict}': {source_url}")
        return _exclude(exclusions, raw, "verdict_unmappable")

    # --- Text fields ---
    evidence_text, conclusion_text = clean_evidence(source_name, title, body_text)
    claim_text, claim_source = extract_claim(source_name, title, evidence_text, conclusion_text)

    share = devanagari_share(title + " " + evidence_text[:2000])
    language = "ne" if share >= 0.5 else "en"

    in_main_benchmark = (
        label_fine in ("FALSE", "MISLEADING")
        and label_source not in BENCHMARK_EXCLUDED_SOURCES
        and language == "ne"
    )

    date_published, date_precision = normalize_date_with_precision(raw_date)

    return NepFakeV2Example(
        example_id=make_example_id(source_name, source_url),
        claim_text=claim_text,
        claim_source=claim_source,
        headline=title,
        verdict_label=verdict_label,
        verdict_label_text=verdict_label_text,
        label_fine=label_fine,
        label_source=label_source,
        in_main_benchmark=in_main_benchmark,
        evidence_text=evidence_text,
        conclusion_text=conclusion_text,
        external_evidence_urls=filter_external_links(raw.get("external_links", []), source_url),
        source_name=source_name,
        source_type="fact_checker",
        source_url=source_url,
        date_published=date_published,
        date_precision=date_precision,
        date_scraped=raw.get("date_scraped", "") or "",
        language=language,
        is_native_nepali=(language == "ne"),
        label_basis="fact_checker_verdict",
        topic_category=detect_topic(title, evidence_text),
        annotator_notes=annotator_notes,
        schema_version=SCHEMA_VERSION,
    )


def load_raw(raw_dirs: dict = None) -> list[dict]:
    """All raw records, source by source, files in name (= date) order."""
    out = []
    for source_name, raw_dir in (raw_dirs or RAW_DIRS).items():
        raw_dir = Path(raw_dir)
        if not raw_dir.exists():
            continue
        for json_file in sorted(raw_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error reading {json_file}: {e}")
                continue
            for r in records:
                r = dict(r)
                r.setdefault("source_name", source_name)
                # The file date is the snapshot date when the record lacks one
                r["date_scraped"] = r.get("date_scraped") or json_file.stem
                out.append(r)
    return out


def normalize_all(references: Optional[dict] = None) -> list[NepFakeV2Example]:
    """
    Normalize every raw article, validate, and record what was left out in
    LAST_EXCLUSIONS. Several snapshots of one URL are all returned; the
    deduplicator keeps the newest.
    """
    references = load_reference_labels() if references is None else references
    exclusions: list[dict] = []
    examples = []
    for raw in load_raw(RAW_DIRS):
        ex = normalize_article(raw, references, exclusions)
        if ex is not None:
            examples.append(ex)

    validation = validate_batch(examples)
    for example, result in validation["invalid"]:
        logger.warning(f"  Invalid: {result}")
        exclusions.append({"source_name": example.source_name,
                           "source_url": example.source_url,
                           "reason": "validation_failed",
                           "date_scraped": example.date_scraped})

    # An exclusion of an older snapshot does not count when a newer snapshot
    # of the same URL is kept (or excluded again): one entry per URL.
    kept_urls = {canonical_url(e.source_url) for e in validation["valid"]}
    latest = {}
    for x in exclusions:
        key = canonical_url(x["source_url"])
        if key in kept_urls:
            continue
        if key not in latest or x["date_scraped"] >= latest[key]["date_scraped"]:
            latest[key] = x
    LAST_EXCLUSIONS[:] = sorted(latest.values(),
                                key=lambda x: (x["source_name"], x["source_url"]))

    logger.info(f"normalized {len(validation['valid'])}, excluded {len(LAST_EXCLUSIONS)}")
    return validation["valid"]
