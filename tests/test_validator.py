"""
Test: schema/validator.py
Verifies validation catches bad records and passes good ones.
"""
import sys
sys.path.insert(0, '.')

from schema.schema import NepFakeV2Example
from schema.validator import validate_example, validate_batch, validate_raw_article, ValidationResult
from schema.schema import RawArticle
from config.settings import SCHEMA_VERSION

errors = []

# --- Helper: build a valid example ---
def make_valid_example(**overrides) -> NepFakeV2Example:
    defaults = dict(
        example_id="NF2_20260825_0001",
        claim_text="यो भाइरल दाबी भ्रामक छ",
        verdict_label=1,
        verdict_label_text="FALSE_MISLEADING",
        evidence_text="यो लेखमा तथ्यजाँच गरिएको छ र दाबी भ्रामक पाइएको छ। " * 5,
        source_name="techpana",
        source_type="fact_checker",
        source_url="https://techpana.com/2026/158464/slug",
        date_published="2026-08-25",
        is_native_nepali=True,
        label_basis="fact_checker_verdict",
        topic_category="politics",
        schema_version=SCHEMA_VERSION,
    )
    defaults.update(overrides)
    return NepFakeV2Example(**defaults)


# --- Valid example passes ---
result = validate_example(make_valid_example())
if not result.is_valid:
    errors.append(f"Valid example failed validation: {result.errors}")

# --- Label 0 passes ---
result = validate_example(make_valid_example(verdict_label=0, verdict_label_text="REAL"))
if not result.is_valid:
    errors.append(f"Label 0 example failed: {result.errors}")

# --- Label 2 passes ---
result = validate_example(make_valid_example(verdict_label=2, verdict_label_text="UNVERIFIED"))
if not result.is_valid:
    errors.append(f"Label 2 example failed: {result.errors}")

# --- Label -1 fails — UNKNOWN must not reach dataset ---
result = validate_example(make_valid_example(verdict_label=-1, verdict_label_text="UNKNOWN"))
if result.is_valid:
    errors.append("Label -1 UNKNOWN passed validation — should fail (not exportable)")

# --- Empty claim_text fails ---
result = validate_example(make_valid_example(claim_text=""))
if result.is_valid:
    errors.append("Empty claim_text passed validation — should fail")

# --- Short claim_text fails ---
result = validate_example(make_valid_example(claim_text="छोटो"))
if result.is_valid:
    errors.append("Too-short claim_text passed validation — should fail")

# --- Empty evidence_text fails ---
result = validate_example(make_valid_example(evidence_text=""))
if result.is_valid:
    errors.append("Empty evidence_text passed validation — should fail")

# --- Invalid source_name fails ---
result = validate_example(make_valid_example(source_name="bbc_nepali"))
if result.is_valid:
    errors.append("Dead source 'bbc_nepali' passed validation — should fail")

result = validate_example(make_valid_example(source_name="nepalcheck"))
if result.is_valid:
    errors.append("Dead source 'nepalcheck' passed validation — should fail")

# --- Invalid source_url fails ---
result = validate_example(make_valid_example(source_url="not-a-url"))
if result.is_valid:
    errors.append("Invalid source_url passed validation — should fail")

# --- Invalid date format fails ---
result = validate_example(make_valid_example(date_published="25 Aug 2026"))
if result.is_valid:
    errors.append("Non-ISO date passed validation — should fail")

# --- Label mismatch fails ---
result = validate_example(make_valid_example(verdict_label=0, verdict_label_text="FALSE_MISLEADING"))
if result.is_valid:
    errors.append("Label mismatch (0 + FALSE_MISLEADING) passed validation — should fail")

# --- label_basis mismatch fails ---
result = validate_example(make_valid_example(
    source_type="fact_checker",
    label_basis="source_credibility"
))
if result.is_valid:
    errors.append("fact_checker with source_credibility label_basis passed — should fail")

# --- Empty example_id fails ---
result = validate_example(make_valid_example(example_id=""))
if result.is_valid:
    errors.append("Empty example_id passed validation — should fail")

# --- Wrong example_id format fails ---
result = validate_example(make_valid_example(example_id="WRONG_FORMAT_001"))
if result.is_valid:
    errors.append("Wrong example_id format passed validation — should fail")

# --- validate_batch separates valid from invalid ---
valid_ex = make_valid_example(example_id="NF2_20260825_0001")
invalid_ex = make_valid_example(example_id="NF2_20260825_0002", claim_text="")

batch_result = validate_batch([valid_ex, invalid_ex])
if len(batch_result["valid"]) != 1:
    errors.append(f"validate_batch valid count: expected 1, got {len(batch_result['valid'])}")
if len(batch_result["invalid"]) != 1:
    errors.append(f"validate_batch invalid count: expected 1, got {len(batch_result['invalid'])}")
if batch_result["stats"]["pass_rate"] != "50.0%":
    errors.append(f"validate_batch pass_rate: expected 50.0%, got {batch_result['stats']['pass_rate']}")

# --- validate_raw_article ---
good_raw = RawArticle(
    source_name="techpana",
    source_url="https://techpana.com/2026/158464/slug",
    title="भाइरल दाबी भ्रामक",
    body_text="यो लेखमा तथ्यजाँच गरिएको छ। " * 10,
    raw_verdict_text="भ्रामक",
    date_published="भदौ ९, २०८३",
    date_scraped="2026-09-01",
)
result = validate_raw_article(good_raw)
if not result.is_valid:
    errors.append(f"Valid RawArticle failed: {result.errors}")

bad_raw = RawArticle(
    source_name="techpana",
    source_url="not-a-url",
    title="",
    body_text="",
    raw_verdict_text="",
    date_published="",
    date_scraped="",
)
result = validate_raw_article(bad_raw)
if result.is_valid:
    errors.append("Invalid RawArticle passed validation — should fail")

if errors:
    print("FAIL — validator errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print("PASS — validator: all checks working correctly")