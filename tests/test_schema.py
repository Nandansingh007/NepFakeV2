"""
Test: schema/schema.py
Verifies dataclass construction, make_example_id, to_dict, from_dict round-trip.
"""
import sys
sys.path.insert(0, '.')

from schema.schema import (
    RawArticle, NepFakeV2Example,
    make_example_id, to_dict, from_dict, validate_label
)
from config.settings import SCHEMA_VERSION, LABELS

errors = []

# --- make_example_id ---
assert make_example_id("2026-08-25", 1)    == "NF2_20260825_0001"
assert make_example_id("2026-08-25", 999)  == "NF2_20260825_0999"
assert make_example_id("2026-08-25", 1000) == "NF2_20260825_1000"
assert make_example_id("", 1)              == "NF2_19700101_0001", \
    f"Empty date fallback failed: {make_example_id('', 1)}"
assert make_example_id(None, 1)            == "NF2_19700101_0001", \
    f"None date fallback failed: {make_example_id(None, 1)}"

# --- validate_label ---
assert validate_label(0)  == True
assert validate_label(1)  == True
assert validate_label(2)  == True
assert validate_label(-1) == True
assert validate_label(3)  == False
assert validate_label(99) == False

# --- NepFakeV2Example construction ---
example = NepFakeV2Example(
    example_id="NF2_20260825_0001",
    claim_text="यो भाइरल दाबी भ्रामक छ",
    verdict_label=1,
    verdict_label_text="FALSE_MISLEADING",
    evidence_text="विस्तृत विवरण यहाँ छ। " * 5,
    source_name="techpana",
    source_type="fact_checker",
    source_url="https://techpana.com/2026/158464/slug",
    date_published="2026-08-25",
    is_native_nepali=True,
    label_basis="fact_checker_verdict",
    topic_category="politics",
    schema_version=SCHEMA_VERSION,
)

if example.schema_version != SCHEMA_VERSION:
    errors.append(f"schema_version mismatch: {example.schema_version} != {SCHEMA_VERSION}")

# --- to_dict ---
d = to_dict(example)

required_keys = [
    'example_id', 'claim_text', 'verdict_label', 'verdict_label_text',
    'evidence_text', 'evidence_sentences', 'external_evidence_urls',
    'source_name', 'source_type', 'source_url', 'source_outlet',
    'date_published', 'is_native_nepali', 'label_basis',
    'topic_category', 'annotator_notes', 'split', 'schema_version'
]
for key in required_keys:
    if key not in d:
        errors.append(f"to_dict() missing key: {key}")

# verdict_label must be int in dict (CSV-safe)
if not isinstance(d['verdict_label'], int):
    errors.append(f"verdict_label not int in dict: {type(d['verdict_label'])}")

# lists serialized as pipe-separated strings
if not isinstance(d['evidence_sentences'], str):
    errors.append(f"evidence_sentences not str in dict: {type(d['evidence_sentences'])}")
if not isinstance(d['external_evidence_urls'], str):
    errors.append(f"external_evidence_urls not str in dict: {type(d['external_evidence_urls'])}")

# --- from_dict round-trip ---
example2 = from_dict(d)

if example2.example_id != example.example_id:
    errors.append(f"Round-trip example_id mismatch: {example2.example_id}")
if example2.verdict_label != example.verdict_label:
    errors.append(f"Round-trip verdict_label mismatch: {example2.verdict_label}")
if example2.claim_text != example.claim_text:
    errors.append(f"Round-trip claim_text mismatch")
if example2.source_name != example.source_name:
    errors.append(f"Round-trip source_name mismatch")

# --- to_dict → from_dict with lists ---
example_with_lists = NepFakeV2Example(
    example_id="NF2_20260825_0002",
    claim_text="अर्को दाबी",
    verdict_label=0,
    verdict_label_text="REAL",
    evidence_text="प्रमाण यहाँ छ। " * 5,
    evidence_sentences=["पहिलो वाक्य", "दोस्रो वाक्य"],
    external_evidence_urls=["https://example.com/1", "https://example.com/2"],
    source_name="nepalfactcheck",
    source_type="fact_checker",
    source_url="https://nepalfactcheck.org/2026/08/slug",
    date_published="2026-08-25",
    label_basis="fact_checker_verdict",
    schema_version=SCHEMA_VERSION,
)
d2 = to_dict(example_with_lists)
ex2 = from_dict(d2)
if ex2.evidence_sentences != ["पहिलो वाक्य", "दोस्रो वाक्य"]:
    errors.append(f"evidence_sentences round-trip failed: {ex2.evidence_sentences}")
if ex2.external_evidence_urls != ["https://example.com/1", "https://example.com/2"]:
    errors.append(f"external_evidence_urls round-trip failed: {ex2.external_evidence_urls}")

# --- RawArticle construction ---
raw = RawArticle(
    source_name="techpana",
    source_url="https://techpana.com/2026/158464/slug",
    title="भाइरल दाबी",
    body_text="विस्तृत विवरण।",
    raw_verdict_text="भ्रामक",
    date_published="भदौ ९, २०८३",
    date_scraped="2026-09-01",
)

# published_date_iso is internal — defaults to empty
if raw.published_date_iso != "":
    errors.append(f"published_date_iso default wrong: {raw.published_date_iso}")

if errors:
    print("FAIL — schema errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print("PASS — schema: construction, make_example_id, to_dict, from_dict all correct")