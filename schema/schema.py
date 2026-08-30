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
    # Which scraper produced this
    # "techpana" / "nepalcheck" / "nepalfactcheck"
    # "bbc_nepali" / "kantipur"

    source_url: str
    # Full URL of the article page

    # --- Raw content ---
    title: str
    # Article headline as it appears on the page

    body_text: str
    # Full article body text — stripped of HTML tags
    # This becomes evidence_text after normalization

    raw_verdict_text: str
    # Verdict exactly as found on the page
    # e.g. "मिथ्या" / "misleading" / "half-truth"
    # Empty string "" for newspaper sources (no verdict)

    date_published: str
    # Date string exactly as found on the page
    # e.g. "August 13, 2026" / "भदौ २८, २०८३"
    # Normalized to ISO format in Stage 2

    date_scraped: str
    # ISO format date when this article was scraped
    # e.g. "2026-08-31"
    # Set by scraper at collection time

    # --- Optional fields ---
    author: str = ""
    # Article author if available, empty string otherwise

    category: str = ""
    # Category tag from the website if available

    external_links: list = field(default_factory=list)
    # All outbound links found in article body
    # Potential evidence URLs — filtered in normalization


# =============================================================================
# STAGE 2 — NEPFAKEV2 EXAMPLE
# Normalized dataset record — what goes into nepfakev2.csv
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
    # Format: NF2_YYYYMMDD_NNNN
    # e.g.   NF2_20260831_0001
    # Assigned by normalizer — never by scraper
    # Stable across dataset versions

    # --- The claim ---
    claim_text: str
    # The claim being verified, in Nepali (Devanagari)
    # For fact-checker sources: extracted from article body
    # For newspaper sources: article headline

    # --- Verdict ---
    verdict_label: int
    # 0 = REAL
    # 1 = FALSE_MISLEADING
    # 2 = UNVERIFIED

    verdict_label_text: str
    # Human readable label
    # "REAL" / "FALSE_MISLEADING" / "UNVERIFIED"

    # --- Evidence ---
    evidence_text: str
    # Full fact-check article body in Nepali
    # This is the evidence document for RAG pipeline
    # For newspaper sources: full article body

    evidence_sentences: list = field(default_factory=list)
    # Key sentences from article that justify the verdict
    # Extracted from evidence_text
    # Enables sentence-level retrieval (FEVER-compatible)

    external_evidence_urls: list = field(default_factory=list)
    # URLs cited by fact-checker as proof
    # e.g. government press releases, official statements
    # Empty list for newspaper sources

    # --- Source metadata ---
    source_name: str = ""
    # "techpana" / "nepalcheck" / "nepalfactcheck"
    # "bbc_nepali" / "kantipur"

    source_type: str = ""
    # "fact_checker" or "newspaper"

    source_url: str = ""
    # Original article URL for verification

    source_outlet: str = ""
    # Outlet that originally published the claim
    # e.g. "Kantipur" / "Setopati" / "Facebook"
    # Relevant for fact-checker sources

    date_published: str = ""
    # ISO format: YYYY-MM-DD
    # Empty string if not found — never None (breaks CSV)

    # --- Quality flags ---
    is_native_nepali: bool = False
    # True if claim_text contains Devanagari script
    # Set by validator using is_devanagari()

    label_basis: str = "fact_checker_verdict"
    # How the label was assigned:
    # "fact_checker_verdict" — verified by professional fact-checker
    # "source_credibility"   — newspaper source, presumed factual
    # Important for paper: documents assumption for Label 0

    topic_category: str = "other"
    # politics / health / society / technology / environment / other
    # Assigned by normalizer using keyword detection

    annotator_notes: str = ""
    # Edge case notes, label disagreements
    # Empty string by default

    split: str = ""
    # "train" / "dev" / "test"
    # Assigned after full dataset is collected
    # Fixed split — reproducible via random seed 42

    # --- Schema version ---
    schema_version: str = field(default_factory=lambda: SCHEMA_VERSION)
    # "1.0" — increment when schema changes
    # Allows old records to be identified and migrated


# =============================================================================
# HELPERS
# =============================================================================

def to_dict(example: NepFakeV2Example) -> dict:
    """
    Convert NepFakeV2Example to a flat dictionary for CSV/JSON export.
    Lists are stored as pipe-separated strings in CSV.
    """
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
    """
    Reconstruct NepFakeV2Example from a CSV/JSON row.
    Inverse of to_dict().
    """
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


def make_example_id(date_str: str, sequence: int) -> str:
    """
    Generate a stable example ID.
    Args:
        date_str: ISO date string e.g. "2026-08-31"
        sequence: Sequential number for this run e.g. 1
    Returns:
        e.g. "NF2_20260831_0001"
    """
    date_compact = date_str.replace("-", "")
    return f"NF2_{date_compact}_{sequence:04d}"