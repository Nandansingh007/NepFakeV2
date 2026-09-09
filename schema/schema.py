# schema/schema.py
# =============================================================================
# NepFakeV2 data schema.
# Defines two dataclasses:
#   1. RawArticle    — output of scrapers (Stage 1)
#   2. NepFakeV2Example — normalized dataset record (Stage 2)
#
# Usage:
#   from schema.schema import RawArticle, NepFakeV2Example, to_dict
# =============================================================================

from dataclasses import dataclass, field
from typing import Optional
from config.settings import SCHEMA_VERSION, LABELS, is_devanagari


# =============================================================================
# STAGE 1 — RAW ARTICLE
# Output of scrapers before normalization
# Stored in raw/<source>/<date>.json
# =============================================================================

@dataclass
class RawArticle:
    """
    Raw scraped article — exactly what the scraper finds on the page.
    No normalization, no label mapping, no cleaning.
    This is the immutable source of truth for each scrape run.
    """

    # --- Identity ---
    source_name: str
    source_url: str

    # --- Raw content ---
    title: str
    body_text: str

    raw_verdict_text: str
    # Verdict exactly as found on the page
    # e.g. "मिथ्या" / "भ्रामक" / ""

    date_published: str
    # Date string EXACTLY as found on the page — NO conversion
    # TechPana:       "भदौ ९, २०८३ १६:८"  ← raw BS string
    # NepalFactCheck: "2026-07-14T14:47:19+05:45" ← raw ISO string
    # Converted to ISO in Stage 2 normalizer

    date_scraped: str
    # ISO format date when this article was scraped
    # e.g. "2026-09-05" — set by scraper

    # --- Internal field for incremental cutoff check ---
    published_date_iso: str = ""
    # ISO date "YYYY-MM-DD" for cutoff comparison ONLY
    # NOT stored in raw JSON — used by base.py paginate()

    # --- Optional fields ---
    author: str = ""
    category: str = ""
    external_links: list = field(default_factory=list)

    annotator_notes: str = ""
    # ← NEW: flags issues found during scraping
    # "verdict_requires_manual_review" if verdict extraction failed
    # Empty string otherwise
    # Stored in raw JSON for Stage 2 human review


# =============================================================================
# STAGE 2 — NEPFAKEV2 EXAMPLE
# =============================================================================

@dataclass
class NepFakeV2Example:
    """
    Normalized NepFakeV2 dataset record.
    One record = one fact-checked claim or one news article.
    This is what researchers use.
    """

    # --- Identity ---
    example_id: str
    claim_text: str

    # --- Verdict ---
    verdict_label: int
    verdict_label_text: str

    # --- Evidence ---
    evidence_text: str
    evidence_sentences: list = field(default_factory=list)
    external_evidence_urls: list = field(default_factory=list)

    # --- Source metadata ---
    source_name: str = ""
    source_type: str = ""
    source_url: str = ""
    source_outlet: str = ""
    date_published: str = ""

    # --- Quality flags ---
    is_native_nepali: bool = False
    label_basis: str = "fact_checker_verdict"
    topic_category: str = "other"
    annotator_notes: str = ""
    split: str = ""

    # --- Schema version ---
    schema_version: str = field(default_factory=lambda: SCHEMA_VERSION)


# =============================================================================
# HELPERS
# =============================================================================

def make_example_id(date_str: str, sequence: int) -> str:
    """
    Generate stable example ID.
    ID format: NF2_YYYYMMDD_NNNN
    e.g. "NF2_20260831_0001"

    Args:
        date_str: ISO date string "YYYY-MM-DD" or "YYYYMMDD"
                  Falls back to "19700101" if empty.
        sequence: Sequential integer — unique within a batch.

    Returns:
        Example ID string.
    """
    date_compact = (date_str or "19700101").replace("-", "")
    return f"NF2_{date_compact}_{sequence:04d}"


def to_dict(example: NepFakeV2Example) -> dict:
    """Convert NepFakeV2Example to flat dict for CSV/JSON export."""
    return {
        "example_id":             example.example_id,
        "claim_text":             example.claim_text,
        "verdict_label":          int(example.verdict_label),
        "verdict_label_text":     example.verdict_label_text,
        "evidence_text":          example.evidence_text,
        "evidence_sentences":     " | ".join(example.evidence_sentences),
        "external_evidence_urls": " | ".join(example.external_evidence_urls),
        "source_name":            example.source_name,
        "source_type":            example.source_type,
        "source_url":             example.source_url,
        "source_outlet":          example.source_outlet,
        "date_published":         example.date_published,
        "is_native_nepali":       example.is_native_nepali,
        "label_basis":            example.label_basis,
        "topic_category":         example.topic_category,
        "annotator_notes":        example.annotator_notes,
        "split":                  example.split,
        "schema_version":         example.schema_version,
    }


def from_dict(d: dict) -> NepFakeV2Example:
    """Reconstruct NepFakeV2Example from CSV/JSON row."""
    return NepFakeV2Example(
        example_id=             d["example_id"],
        claim_text=             d["claim_text"],
        verdict_label=          int(d["verdict_label"]),
        verdict_label_text=     d["verdict_label_text"],
        evidence_text=          d["evidence_text"],
        evidence_sentences=     d["evidence_sentences"].split(" | ") if d["evidence_sentences"] else [],
        external_evidence_urls= d["external_evidence_urls"].split(" | ") if d["external_evidence_urls"] else [],
        source_name=            d.get("source_name", ""),
        source_type=            d.get("source_type", ""),
        source_url=             d.get("source_url", ""),
        source_outlet=          d.get("source_outlet", ""),
        date_published=         d.get("date_published", ""),
        is_native_nepali=       d.get("is_native_nepali", False),
        label_basis=            d.get("label_basis", "fact_checker_verdict"),
        topic_category=         d.get("topic_category", "other"),
        annotator_notes=        d.get("annotator_notes", ""),
        split=                  d.get("split", ""),
        schema_version=         d.get("schema_version", SCHEMA_VERSION),
    )


def validate_label(label: int) -> bool:
    """Returns True if label is a valid NepFakeV2 label."""
    return label in LABELS