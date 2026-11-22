"""
Test: schema/schema.py
Dataclass construction, make_example_id, to_dict / from_dict round-trip.
"""
import pytest

from schema.schema import (
    RawArticle, NepFakeV2Example,
    make_example_id, to_dict, from_dict, validate_label,
)
from config.settings import SCHEMA_VERSION


@pytest.mark.parametrize(
    "date, n, expected",
    [
        ("2026-08-25", 1, "NF2_20260825_0001"),
        ("2026-08-25", 999, "NF2_20260825_0999"),
        ("2026-08-25", 1000, "NF2_20260825_1000"),
        ("", 1, "NF2_19700101_0001"),
        (None, 1, "NF2_19700101_0001"),
    ],
)
def test_make_example_id(date, n, expected):
    assert make_example_id(date, n) == expected


@pytest.mark.parametrize(
    "label, ok", [(0, True), (1, True), (2, True), (-1, True), (3, False), (99, False)]
)
def test_validate_label(label, ok):
    assert validate_label(label) is ok


@pytest.fixture
def example():
    return NepFakeV2Example(
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


def test_schema_version_set(example):
    assert example.schema_version == SCHEMA_VERSION


def test_to_dict_keys_and_types(example):
    d = to_dict(example)
    required_keys = [
        'example_id', 'claim_text', 'verdict_label', 'verdict_label_text',
        'evidence_text', 'evidence_sentences', 'external_evidence_urls',
        'source_name', 'source_type', 'source_url', 'source_outlet',
        'date_published', 'is_native_nepali', 'label_basis',
        'topic_category', 'annotator_notes', 'split', 'schema_version',
    ]
    missing = [k for k in required_keys if k not in d]
    assert not missing, f"to_dict() missing keys: {missing}"
    assert isinstance(d['verdict_label'], int)  # CSV-safe
    # lists are serialized as pipe-separated strings
    assert isinstance(d['evidence_sentences'], str)
    assert isinstance(d['external_evidence_urls'], str)


def test_from_dict_round_trip(example):
    ex2 = from_dict(to_dict(example))
    assert ex2.example_id == example.example_id
    assert ex2.verdict_label == example.verdict_label
    assert ex2.claim_text == example.claim_text
    assert ex2.source_name == example.source_name


def test_round_trip_with_lists():
    ex = NepFakeV2Example(
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
    ex2 = from_dict(to_dict(ex))
    assert ex2.evidence_sentences == ["पहिलो वाक्य", "दोस्रो वाक्य"]
    assert ex2.external_evidence_urls == ["https://example.com/1", "https://example.com/2"]


def test_raw_article_iso_date_defaults_empty():
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
    assert raw.published_date_iso == ""
