# pipeline/normalizer.py
# =============================================================================
# Normalizes raw scraped articles into NepFakeV2Example records.
#
# Input:  RawArticle dicts from raw JSON files
# Output: NepFakeV2Example dataclass instances
#
# Jobs:
#   - Map raw verdict → label 0/1/2
#   - Convert raw date → ISO format
#   - Assign example_id
#   - Detect Devanagari script
#   - Assign topic_category
#   - Set source metadata
#
# Usage:
#   from pipeline.normalizer import normalize_article, normalize_all
# =============================================================================

import re
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import is_devanagari, RAW_DIRS, SCHEMA_VERSION
from schema.schema import NepFakeV2Example, make_example_id
from pipeline.label_mapper import map_verdict, is_mappable
from scrapers.techpana import BS_MONTHS, parse_bs_date

logger = logging.getLogger("nepfakev2.normalizer")


# =============================================================================
# DATE NORMALIZATION
# =============================================================================

def normalize_date(raw_date: str) -> str:
    """
    Convert raw date string to ISO format YYYY-MM-DD.

    Handles:
        BS strings:  "भदौ ९, २०८३"          → "2026-08-25"
        ISO strings: "2026-07-14T14:47:19"   → "2026-07-14"
        Year only:   "2026"                   → "2026-01-01"
        Empty:       ""                        → ""

    Args:
        raw_date: Raw date string from scraper

    Returns:
        ISO date string "YYYY-MM-DD" or "" if cannot parse
    """
    if not raw_date or not raw_date.strip():
        return ""

    raw_date = raw_date.strip()

    # ISO format — starts with digit and has dashes
    if raw_date[0].isdigit():
        # Full ISO datetime: "2026-07-14T14:47:19+05:45"
        if "T" in raw_date:
            return raw_date[:10]
        # ISO date: "2026-07-14"
        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
            return raw_date
        # Year-month: "2026-08"
        if re.match(r"^\d{4}-\d{2}$", raw_date):
            return f"{raw_date}-01"
        # Year only: "2026"
        if re.match(r"^\d{4}$", raw_date):
            return f"{raw_date}-01-01"

    # BS date string — starts with Nepali month name
    for month in BS_MONTHS.keys():
        if raw_date.startswith(month):
            converted = parse_bs_date(raw_date)
            if converted:
                return converted
            break

    logger.warning(f"Could not parse date: {raw_date}")
    return ""


# =============================================================================
# TOPIC CATEGORY DETECTION
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
    """
    Detect topic category from article title and body.
    Uses keyword matching — imperfect but good enough for metadata.

    Args:
        title:     Article headline
        body_text: Article body text

    Returns:
        Topic string: "politics" / "health" / "technology" /
                      "society" / "environment" / "economy" / "other"
    """
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
# NORMALIZER
# =============================================================================

# Counter for generating sequential example IDs
_id_counter = 0


def reset_id_counter():
    """Reset ID counter — call before normalizing a full batch."""
    global _id_counter
    _id_counter = 0


def normalize_article(
    raw: dict,
    sequence: int,
) -> Optional[NepFakeV2Example]:
    """
    Normalize a single raw article dict into a NepFakeV2Example.

    Args:
        raw:      Raw article dict from JSON file
        sequence: Sequential number for example_id generation

    Returns:
        NepFakeV2Example if normalization succeeds
        None if article should be skipped (unmappable verdict etc.)
    """
    source_name = raw.get("source_name", "")
    source_url = raw.get("source_url", "")
    title = raw.get("title", "").strip()
    body_text = raw.get("body_text", "").strip()
    raw_verdict = raw.get("raw_verdict_text", "").strip()
    raw_date = raw.get("date_published", "")
    annotator_notes = raw.get("annotator_notes", "")

    # --- Skip if no title or body ---
    if not title or not body_text:
        logger.warning(f"Skipping — no title or body: {source_url}")
        return None

    # --- Map verdict to label ---
    verdict_label, verdict_label_text = map_verdict(raw_verdict)

    # Skip unmappable verdicts — flag for manual review
    if verdict_label == -1:
        logger.warning(f"Unmappable verdict '{raw_verdict}': {source_url}")
        if annotator_notes:
            annotator_notes += " | verdict_unmappable"
        else:
            annotator_notes = "verdict_unmappable"

    # --- Normalize date ---
    date_published = normalize_date(raw_date)

    # --- Generate example ID ---
    date_for_id = date_published or "19700101"
    date_compact = date_for_id.replace("-", "")
    example_id = f"NF2_{date_compact}_{sequence:04d}"

    # --- Detect Devanagari ---
    is_native_nepali = is_devanagari(title) or is_devanagari(body_text[:100])

    # --- Detect topic ---
    topic_category = detect_topic(title, body_text)

    # --- Set source type ---
    source_type = "fact_checker"  # all active sources are fact-checkers

    # --- Set label basis ---
    label_basis = "fact_checker_verdict"

    # --- Build example ---
    example = NepFakeV2Example(
        example_id=example_id,
        claim_text=title,
        verdict_label=verdict_label if verdict_label != -1 else 1,
        verdict_label_text=verdict_label_text if verdict_label != -1 else "FALSE_MISLEADING",
        evidence_text=body_text,
        evidence_sentences=[],
        external_evidence_urls=raw.get("external_links", [])[:5],
        source_name=source_name,
        source_type=source_type,
        source_url=source_url,
        source_outlet="",
        date_published=date_published,
        is_native_nepali=is_native_nepali,
        label_basis=label_basis,
        topic_category=topic_category,
        annotator_notes=annotator_notes,
        split="",
        schema_version=SCHEMA_VERSION,
    )

    return example


def normalize_all() -> list[NepFakeV2Example]:
    """
    Normalize all raw articles from all sources.
    Reads all JSON files from raw/ directories.

    Returns:
        List of NepFakeV2Example records
    """
    reset_id_counter()
    all_examples = []
    sequence = 1

    for source_name, raw_dir in RAW_DIRS.items():
        raw_dir = Path(raw_dir)
        if not raw_dir.exists():
            continue

        json_files = sorted(raw_dir.glob("*.json"))
        if not json_files:
            continue

        source_articles = []
        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                source_articles.extend(articles)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Error reading {json_file}: {e}")

        logger.info(
            f"{source_name}: loaded {len(source_articles)} raw articles"
        )

        # Normalize each article
        for raw in source_articles:
            example = normalize_article(raw, sequence)
            if example:
                all_examples.append(example)
                sequence += 1

        logger.info(
            f"{source_name}: normalized {len(all_examples)} examples so far"
        )

    logger.info(f"Total normalized: {len(all_examples)} examples")
    return all_examples