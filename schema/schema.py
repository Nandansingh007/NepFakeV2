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
    # Verdict the scraper chose, e.g. "मिथ्या" / "भ्रामक" / ""
    # TechPana since 2026-11-23: conclusion, then lead summary, then the
    # og:image badge (scrapers/techpana.py resolve_verdict). Older files
    # hold the badge first, and before 12 Oct 2026 sometimes a sidebar badge.

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

    badge_url: str = ""
    # TechPana (since Nov 2026): the og:image URL the badge verdict is read
    # from, so a badge that changes between scrapes can be shown. "" if none.

    page_complete: Optional[bool] = None
    # TechPana (since Nov 2026): True if the article text reached the end of
    # the page (the "पछिल्ला अपडेट" sidebar), False if it was still cut short
    # after the retries, None for files written before the check existed.

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
    # Stable ID from the URL (schema 2.0): NF2_tp_<article number> or
    # NF2_nfc_<10 hex of sha1(canonical URL)>. See make_example_id().
    claim_text: str
    # The claim being checked, extracted from the article (schema 2.0).
    # Before 2.0 this was the fact-checker's headline, which states the
    # verdict. How it was found: claim_source.

    # --- Verdict ---
    verdict_label: int
    verdict_label_text: str

    # --- Evidence ---
    evidence_text: str
    # Article body without header, conclusion, footer/sidebar and without
    # any sentence that states the verdict (schema 2.0). The full body is
    # in raw/ only.
    external_evidence_urls: list = field(default_factory=list)
    # Links in the article, minus share buttons and the outlet's own pages

    # --- Text provenance (schema 2.0) ---
    claim_source: str = ""
    # config/settings.py CLAIM_SOURCES: claim_box / headline_question /
    # claim_caption / lead_quote / lead / claim_section / headline /
    # hand_checked
    claimant: str = ""
    # Who made the claim, as the fact-checker names it (NFC "दावीकर्ता";
    # TechPana only from the hand check). Empty if not given.
    claim_platform: str = ""
    # Where the claim spread, "|"-joined: facebook / tiktok / x / youtube /
    # instagram / messaging / news_media. From the claimant line and
    # TechPana's "दाबी" section, or the hand check. Empty = not stated.
    headline: str = ""
    # The fact-checker's headline. It usually states the verdict: never a
    # model input for the main task.
    conclusion_text: str = ""
    # The fact-checker's conclusion. States the verdict: never a model input.

    # --- Source metadata ---
    source_name: str = ""
    source_type: str = ""
    source_url: str = ""
    date_published: str = ""
    date_precision: str = ""
    # day / month / year: a year-only date is stored as YYYY-01-01
    date_scraped: str = ""
    # Snapshot this record was built from (raw file date). Dedup keeps the
    # newest snapshot of each article.

    # --- Quality flags ---
    language: str = ""
    # "ne" or "en" (share of Devanagari letters in headline + evidence)
    is_native_nepali: bool = False
    # language == "ne". (Not "written by a Nepali": all rows are Nepali outlets)
    label_basis: str = "fact_checker_verdict"
    label_source: str = ""
    verified: str = "silver"
    # gold: a person checked the label (data_validation/reference_labels.csv,
    # label_source "hand_checked"). silver: label read from the article by
    # the rules only. pipeline/evaluate.py --gold scores gold rows only.
    # Where the verdict was read (config/settings.py LABEL_SOURCES):
    #   nfc_header / conclusion / conclusion_claim / conclusion_mixed /
    #   summary / stored /
    #   hand_checked
    snapshot_conflict: bool = False
    # True if another snapshot of the same article had a different label_fine
    # (pipeline/deduplicator.py picks one copy by a fixed rule; the copy is
    # used whole). Listed in logs/snapshot_report.json after each build.
    snapshot_other_label: str = ""
    # label_fine of the other snapshot(s), several joined with "|"; "" if none
    snapshot_source: str = "live"
    # Where the kept copy is stored: "live" (raw/<source>/, the latest full
    # re-scrape and the weekly runs after it) or "archive" (raw/archive/,
    # used only when no live copy of the article is usable, e.g. the live copy
    # has no verdict or the article was not listed in the latest scrape).
    label_fine: str = ""
    # Fine label (schema 2.0): FALSE / MISLEADING / TRUE / UNVERIFIED.
    # verdict_label stays the coarse label; see config/settings.py LABELS_FINE.
    in_main_benchmark: bool = False
    benchmark_exclusion_reason: str = ""
    # Why the row is not in the benchmark ("" if it is): label_<LABEL>,
    # label_source_<SOURCE>, language_en, page_cut, several joined with "|"
    # (pipeline/normalizer.py benchmark_reasons).
    # True if the row belongs to the main FALSE-vs-MISLEADING task:
    # label_fine is FALSE or MISLEADING, label_source is not in
    # BENCHMARK_EXCLUDED_SOURCES, and language is "ne".
    topic_category: str = "other"
    annotator_notes: str = ""

    # --- Splits (schema 2.0, pipeline/splitter.py) ---
    claim_group_id: str = ""
    # Rows about the same claim share this ID (never split across splits)
    split: str = ""
    # Time split: train / dev / test (frozen file), "new" for rows added
    # after the freeze
    split_random: str = ""
    # Control split: random by claim group, same frozen file

    # --- Schema version ---
    schema_version: str = field(default_factory=lambda: SCHEMA_VERSION)


# =============================================================================
# HELPERS
# =============================================================================

def make_example_id(source_name: str, source_url: str) -> str:
    """
    Stable example ID, derived from the article itself (schema 2.0).

        TechPana:        the article number in the URL   -> "NF2_tp_159019"
        NepalFactCheck:  10 hex chars of sha1(canonical URL) -> "NF2_nfc_3f9a0c1b2d"
        anything else:   "NF2_<source>_<hash>"

    It does not depend on dates, file order or other articles, so adding a
    raw file, re-scraping or correcting a date never changes an ID.
    (Before 2.0 the ID was NF2_<date>_<running number>; see
    data/id_map_v1_to_v2.csv.)
    """
    import hashlib
    import re
    from utils.helpers import canonical_url

    url = canonical_url(source_url)
    if source_name == "techpana":
        m = re.search(r"techpana\.com/\d{4}/(\d+)(?:/|$)", url)
        if m:
            return f"NF2_tp_{m.group(1)}"
    short = {"nepalfactcheck": "nfc"}.get(source_name, source_name or "x")
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    return f"NF2_{short}_{digest}"


# Column order of data/nepfakev2.csv (schema 2.0)
COLUMNS = [
    "example_id", "claim_text", "claim_source", "claimant", "claim_platform",
    "headline", "verdict_label", "verdict_label_text", "label_fine",
    "label_source", "verified", "snapshot_conflict", "snapshot_other_label",
    "snapshot_source", "in_main_benchmark", "benchmark_exclusion_reason", "evidence_text", "conclusion_text",
    "external_evidence_urls", "source_name", "source_type", "source_url",
    "date_published", "date_precision", "date_scraped", "language",
    "is_native_nepali", "label_basis", "topic_category", "annotator_notes",
    "claim_group_id", "split", "split_random", "schema_version",
]


def to_dict(example: NepFakeV2Example) -> dict:
    """Convert NepFakeV2Example to a flat dict (CSV/JSON), in COLUMNS order."""
    d = {name: getattr(example, name) for name in COLUMNS}
    d["verdict_label"] = int(example.verdict_label)
    d["in_main_benchmark"] = bool(example.in_main_benchmark)
    d["is_native_nepali"] = bool(example.is_native_nepali)
    d["snapshot_conflict"] = bool(example.snapshot_conflict)
    d["external_evidence_urls"] = " | ".join(example.external_evidence_urls)
    return d


def _as_bool(value) -> bool:
    """CSV gives "True"/"False" strings; "False" must not read as True."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes")


def _as_str(value) -> str:
    """pandas gives NaN for an empty CSV cell."""
    if value is None or (isinstance(value, float) and value != value):
        return ""
    return str(value)


def from_dict(d: dict) -> NepFakeV2Example:
    """Reconstruct NepFakeV2Example from a CSV/JSON row (2.0 columns)."""
    urls = _as_str(d.get("external_evidence_urls", ""))
    kw = {name: _as_str(d.get(name, "")) for name in COLUMNS
          if name not in ("verdict_label", "in_main_benchmark", "is_native_nepali",
                          "snapshot_conflict", "external_evidence_urls")}
    kw["topic_category"] = kw["topic_category"] or "other"
    kw["label_basis"] = kw["label_basis"] or "fact_checker_verdict"
    kw["schema_version"] = kw["schema_version"] or SCHEMA_VERSION
    kw["verified"] = kw["verified"] or "silver"
    return NepFakeV2Example(
        verdict_label=int(d["verdict_label"]),
        in_main_benchmark=_as_bool(d.get("in_main_benchmark", False)),
        is_native_nepali=_as_bool(d.get("is_native_nepali", False)),
        snapshot_conflict=_as_bool(d.get("snapshot_conflict", False)),
        external_evidence_urls=urls.split(" | ") if urls else [],
        **kw,
    )


def validate_label(label: int) -> bool:
    """Returns True if label is a valid NepFakeV2 label."""
    return label in LABELS