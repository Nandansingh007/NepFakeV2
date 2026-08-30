# schema/validator.py
# =============================================================================
# Validation functions for NepFakeV2Example records.
# Called by the pipeline after normalization to catch bad records
# before they enter the dataset.
#
# Usage:
#   from schema.validator import validate_example, ValidationResult
# =============================================================================

from dataclasses import dataclass
from typing import List
from schema.schema import NepFakeV2Example, RawArticle
from config.settings import LABELS, is_devanagari


# =============================================================================
# VALIDATION RESULT
# =============================================================================

@dataclass
class ValidationResult:
    """
    Result of validating a single NepFakeV2Example.
    
    Attributes:
        is_valid:  True if record passes all checks
        errors:    List of hard failures — record must be fixed or dropped
        warnings:  List of soft issues — record is kept but flagged
        example_id: ID of the record being validated
    """
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    example_id: str = ""

    def __str__(self):
        lines = [f"ValidationResult for {self.example_id}"]
        lines.append(f"  Valid: {self.is_valid}")
        if self.errors:
            lines.append(f"  Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"    - {e}")
        if self.warnings:
            lines.append(f"  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# =============================================================================
# EXAMPLE VALIDATOR
# =============================================================================

def validate_example(example: NepFakeV2Example) -> ValidationResult:
    """
    Validate a single NepFakeV2Example record.
    
    Hard errors → record is dropped from dataset
    Warnings    → record is kept but flagged in annotator_notes
    
    Args:
        example: NepFakeV2Example to validate
    
    Returns:
        ValidationResult with errors and warnings
    """
    errors = []
    warnings = []

    # --- example_id ---
    if not example.example_id:
        errors.append("example_id is empty")
    elif not example.example_id.startswith("NF2_"):
        errors.append(f"example_id format invalid: {example.example_id}")

    # --- claim_text ---
    if not example.claim_text or not example.claim_text.strip():
        errors.append("claim_text is empty")
    elif len(example.claim_text.strip()) < 10:
        errors.append(f"claim_text too short ({len(example.claim_text)} chars): {example.claim_text}")
    
    if example.claim_text and not is_devanagari(example.claim_text):
        warnings.append("claim_text contains no Devanagari script")

    # --- verdict_label ---
    if example.verdict_label not in LABELS:
        errors.append(f"verdict_label invalid: {example.verdict_label} — must be one of {list(LABELS.keys())}")

    # --- verdict_label_text ---
    if not example.verdict_label_text:
        errors.append("verdict_label_text is empty")
    elif example.verdict_label_text not in LABELS.values():
        errors.append(f"verdict_label_text invalid: {example.verdict_label_text}")

    # --- label consistency ---
    if (example.verdict_label in LABELS and
        example.verdict_label_text and
        LABELS.get(example.verdict_label) != example.verdict_label_text):
        errors.append(
            f"label mismatch: verdict_label={example.verdict_label} "
            f"but verdict_label_text='{example.verdict_label_text}' "
            f"(expected '{LABELS.get(example.verdict_label)}')"
        )

    # --- evidence_text ---
    if not example.evidence_text or not example.evidence_text.strip():
        errors.append("evidence_text is empty")
    elif len(example.evidence_text.strip()) < 50:
        warnings.append(f"evidence_text very short ({len(example.evidence_text)} chars)")

    # --- source_name ---
    valid_sources = {
        "techpana", "nepalcheck", "nepalfactcheck",
        "bbc_nepali", "kantipur"
    }
    if not example.source_name:
        errors.append("source_name is empty")
    elif example.source_name not in valid_sources:
        errors.append(f"source_name unknown: {example.source_name}")

    # --- source_type ---
    valid_source_types = {"fact_checker", "newspaper"}
    if not example.source_type:
        errors.append("source_type is empty")
    elif example.source_type not in valid_source_types:
        errors.append(f"source_type invalid: {example.source_type}")

    # --- source_url ---
    if not example.source_url:
        errors.append("source_url is empty")
    elif not example.source_url.startswith("http"):
        errors.append(f"source_url invalid: {example.source_url}")

    # --- date_published ---
    if not example.date_published:
        warnings.append("date_published is empty")
    else:
        # Must be ISO format YYYY-MM-DD
        import re
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", example.date_published):
            errors.append(f"date_published not ISO format: {example.date_published}")

    # --- label_basis ---
    valid_bases = {"fact_checker_verdict", "source_credibility"}
    if example.label_basis not in valid_bases:
        errors.append(f"label_basis invalid: {example.label_basis}")

    # --- label_basis consistency ---
    # Newspaper sources must use source_credibility
    if example.source_type == "newspaper" and example.label_basis != "source_credibility":
        errors.append(
            f"newspaper source must have label_basis='source_credibility', "
            f"got '{example.label_basis}'"
        )

    # Fact-checker sources must use fact_checker_verdict
    if example.source_type == "fact_checker" and example.label_basis != "fact_checker_verdict":
        errors.append(
            f"fact_checker source must have label_basis='fact_checker_verdict', "
            f"got '{example.label_basis}'"
        )

    # --- is_native_nepali consistency ---
    if example.is_native_nepali and not is_devanagari(example.claim_text):
        warnings.append("is_native_nepali=True but no Devanagari found in claim_text")

    # --- schema_version ---
    if not example.schema_version:
        errors.append("schema_version is empty")

    # --- warnings for missing optional fields ---
    if not example.evidence_sentences:
        warnings.append("evidence_sentences is empty")

    if not example.topic_category or example.topic_category == "other":
        warnings.append("topic_category is 'other' — may need manual review")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        example_id=example.example_id,
    )


# =============================================================================
# BATCH VALIDATOR
# =============================================================================

def validate_batch(examples: List[NepFakeV2Example]) -> dict:
    """
    Validate a list of NepFakeV2Example records.
    
    Args:
        examples: List of NepFakeV2Example to validate
    
    Returns:
        Dict with keys:
            valid:    list of valid NepFakeV2Example
            invalid:  list of (NepFakeV2Example, ValidationResult) tuples
            stats:    summary statistics
    """
    valid = []
    invalid = []

    for example in examples:
        result = validate_example(example)
        if result.is_valid:
            valid.append(example)
        else:
            invalid.append((example, result))

    stats = {
        "total":   len(examples),
        "valid":   len(valid),
        "invalid": len(invalid),
        "pass_rate": f"{len(valid) / len(examples) * 100:.1f}%" if examples else "0%",
    }

    return {
        "valid":   valid,
        "invalid": invalid,
        "stats":   stats,
    }


# =============================================================================
# RAW ARTICLE VALIDATOR
# =============================================================================

def validate_raw_article(article: RawArticle) -> ValidationResult:
    """
    Validate a RawArticle before it enters normalization.
    Catches bad scrapes early — before normalization wastes time on them.
    
    Args:
        article: RawArticle to validate
    
    Returns:
        ValidationResult with errors and warnings
    """
    errors = []
    warnings = []

    if not article.source_url or not article.source_url.startswith("http"):
        errors.append(f"source_url invalid: {article.source_url}")

    if not article.title or not article.title.strip():
        errors.append("title is empty")

    if not article.body_text or not article.body_text.strip():
        errors.append("body_text is empty")
    elif len(article.body_text.strip()) < 100:
        warnings.append(f"body_text very short ({len(article.body_text)} chars)")

    if not article.date_scraped:
        errors.append("date_scraped is empty")

    if not article.source_name:
        errors.append("source_name is empty")

    return ValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        example_id=article.source_url,
    )