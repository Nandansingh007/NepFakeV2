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
    "source, url, expected",
    [
        ("techpana", "https://techpana.com/2026/158464/slug", "NF2_tp_158464"),
        ("techpana", "https://www.techpana.com/2025/149828/x/?tab=nepali", "NF2_tp_149828"),
    ],
)
def test_make_example_id(source, url, expected):
    # Schema 2.0: from the URL, not from (date, running number). More in
    # tests/test_identity_and_snapshots.py
    assert make_example_id(source, url) == expected


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
    from schema.schema import COLUMNS
    assert list(d) == COLUMNS
    # evidence_sentences and source_outlet were always empty: removed in 2.0
    assert "evidence_sentences" not in d and "source_outlet" not in d
    assert isinstance(d['verdict_label'], int)  # CSV-safe
    # lists are serialized as pipe-separated strings
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
        claim_source="lead", headline="शीर्षक", conclusion_text="निष्कर्ष",
        date_precision="day", language="ne", claim_group_id="G_tp_1",
        split="train", split_random="dev",
        external_evidence_urls=["https://example.com/1", "https://example.com/2"],
        source_name="nepalfactcheck",
        source_type="fact_checker",
        source_url="https://nepalfactcheck.org/2026/08/slug",
        date_published="2026-08-25",
        label_basis="fact_checker_verdict",
        schema_version=SCHEMA_VERSION,
    )
    ex2 = from_dict(to_dict(ex))
    assert (ex2.claim_source, ex2.headline, ex2.conclusion_text) == ("lead", "शीर्षक", "निष्कर्ष")
    assert (ex2.date_precision, ex2.language, ex2.claim_group_id) == ("day", "ne", "G_tp_1")
    assert (ex2.split, ex2.split_random) == ("train", "dev")
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


def test_from_dict_reads_empty_csv_cells():
    # pandas gives NaN (a float) for an empty cell; it must come back as ""
    d = to_dict(NepFakeV2Example(
        example_id="NF2_tp_1", claim_text="दाबी यहाँ छ", verdict_label=1,
        verdict_label_text="FALSE_MISLEADING", evidence_text="प्रमाण"))
    d["conclusion_text"] = float("nan")
    d["is_native_nepali"] = "False"
    ex = from_dict(d)
    assert ex.conclusion_text == "" and ex.is_native_nepali is False
