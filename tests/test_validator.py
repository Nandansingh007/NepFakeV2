"""
Test: schema/validator.py
Validation catches bad records and passes good ones.
"""
import pytest

from schema.schema import NepFakeV2Example, RawArticle
from schema.validator import validate_example, validate_batch, validate_raw_article
from config.settings import SCHEMA_VERSION


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


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"verdict_label": 0, "verdict_label_text": "REAL"},
        {"verdict_label": 2, "verdict_label_text": "UNVERIFIED"},
    ],
    ids=["label1", "label0", "label2"],
)
def test_valid_examples_pass(overrides):
    result = validate_example(make_valid_example(**overrides))
    assert result.is_valid, result.errors


@pytest.mark.parametrize(
    "overrides",
    [
        {"verdict_label": -1, "verdict_label_text": "UNKNOWN"},
        {"claim_text": ""},
        {"claim_text": "छोटो"},
        {"evidence_text": ""},
        {"source_name": "bbc_nepali"},
        {"source_name": "nepalcheck"},
        {"source_url": "not-a-url"},
        {"date_published": "25 Aug 2026"},
        {"verdict_label": 0, "verdict_label_text": "FALSE_MISLEADING"},
        {"source_type": "fact_checker", "label_basis": "source_credibility"},
        {"example_id": ""},
        {"example_id": "WRONG_FORMAT_001"},
    ],
    ids=[
        "unknown_label", "empty_claim", "short_claim", "empty_evidence",
        "dead_source_bbc", "dead_source_nepalcheck", "bad_url", "non_iso_date",
        "label_text_mismatch", "label_basis_mismatch", "empty_id", "bad_id_format",
    ],
)
def test_invalid_examples_fail(overrides):
    result = validate_example(make_valid_example(**overrides))
    assert not result.is_valid


def test_validate_batch_splits_valid_and_invalid():
    batch = validate_batch([
        make_valid_example(example_id="NF2_20260825_0001"),
        make_valid_example(example_id="NF2_20260825_0002", claim_text=""),
    ])
    assert len(batch["valid"]) == 1
    assert len(batch["invalid"]) == 1
    assert batch["stats"]["pass_rate"] == "50.0%"


def test_validate_raw_article_good():
    raw = RawArticle(
        source_name="techpana",
        source_url="https://techpana.com/2026/158464/slug",
        title="भाइरल दाबी भ्रामक",
        body_text="यो लेखमा तथ्यजाँच गरिएको छ। " * 10,
        raw_verdict_text="भ्रामक",
        date_published="भदौ ९, २०८३",
        date_scraped="2026-09-01",
    )
    result = validate_raw_article(raw)
    assert result.is_valid, result.errors


def test_validate_raw_article_bad():
    raw = RawArticle(
        source_name="techpana", source_url="not-a-url", title="", body_text="",
        raw_verdict_text="", date_published="", date_scraped="",
    )
    assert not validate_raw_article(raw).is_valid
