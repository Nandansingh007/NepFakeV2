"""
Test: one verdict rule for TechPana (Phase 1, fix 1).

scrapers/techpana.py resolve_verdict() is used by BOTH the scraper and the
normalizer. Order: conclusion box, then lead summary, then the stored value
(og:image badge). It also returns where the verdict came from, which the
dataset stores as label_source (schema 1.1).

Before this fix the scraper read the badge FIRST and the normalizer read the
conclusion first, so 54 raw TechPana verdicts disagreed with the dataset.
"""
import json
from pathlib import Path

import pytest

from config import settings

# Read lazily so this file still collects (and fails test by test) on code
# from before the fix, where LABEL_SOURCES does not exist yet.
LABEL_SOURCES = getattr(settings, "LABEL_SOURCES", {})
SCHEMA_VERSION = settings.SCHEMA_VERSION


# -----------------------------------------------------------------------------
# Small article bodies, shaped like TechPana's body_text
# -----------------------------------------------------------------------------

HEAD = "फ्याक्टचेक: भाइरल दाबी\nटेकपाना\nभदौ २५, २०८३ १९:२३\n"


def body(summary="", conclusion=None):
    """Title / author / date, a lead summary, the दाबी box, optional निष्कर्ष."""
    text = HEAD + "काठमाडौं । सामाजिक सञ्जालमा एउटा तस्बिर भाइरल छ । " + summary + "\n"
    text += "दाबी\nफेसबुकमा एउटा पोस्ट गरिएको छ ।\nअनुसन्धान\nविवरण यहाँ छ ।\n"
    if conclusion is not None:
        text += "निष्कर्ष\n" + conclusion + "\n"
    text += "प्रतिक्रिया\nसम्बन्धित समाचार\nअर्को दाबी सही हो\n"
    return text


FINDING_FALSE = "तर, टेकपाना फ्याक्टचेक डेस्कको अनुसन्धानबाट उक्त दाबी मिथ्या रहेको पुष्टि भएको छ ।"
FINDING_MISLEADING = "तर, टेकपाना फ्याक्टचेक डेस्कको अनुसन्धानबाट उक्त दाबी भ्रामक रहेको पुष्टि भएको छ ।"


# -----------------------------------------------------------------------------
# named_verdicts: the word rules shared by conclusion and summary
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("दाबी मिथ्या हो", {"मिथ्या"}),
        ("दाबी पूर्णतः भ्रामक र मिथ्या हो", {"मिथ्या", "भ्रामक"}),
        ("दाबी सही होइन", set()),          # negated "true" is not a verdict
        ("भ्रमण गर्न गएका", set()),        # whole words only: भ्रमण ≠ भ्रम
        ("दाबी गलत हो", {"मिथ्या"}),        # the claim is wrong = FALSE (28 Nov 2026)
        ("दाबी गलत भएको देखिएको छ", {"मिथ्या"}),
        ("भिडिओ गलत सन्दर्भमा फैलाइएको", {"भ्रामक"}),   # wrong context = MISLEADING
        ("गलत अर्थ लगाइएको", {"भ्रामक"}),
        ("गलत सूचना फैलाउने कार्य", set()),   # "misinformation" in general: no verdict
        ("गलत र अतिरञ्जित प्रचार", set()),
        ("", set()),
    ],
)
def test_named_verdicts(text, expected):
    from scrapers.techpana import named_verdicts
    assert named_verdicts(text) == expected


# -----------------------------------------------------------------------------
# resolve_verdict: the order and the label_source it reports
# -----------------------------------------------------------------------------

def test_conclusion_beats_badge():
    # The real 159798 case: badge said भ्रामक, conclusion "दाबी मिथ्या हो"
    from scrapers.techpana import resolve_verdict
    b = body(conclusion="भाइरल भिडिओ एआई निर्मित हो । दाबी मिथ्या हो ।")
    assert resolve_verdict(b, "भ्रामक") == ("मिथ्या", "conclusion")


def test_mixed_conclusion_is_marked_and_summary_not_used():
    # Both labels, also in the claim sentence: MISLEADING (28 Nov 2026),
    # marked conclusion_mixed. The summary (मिथ्या here) is NOT used.
    from scrapers.techpana import resolve_verdict
    b = body(summary=FINDING_FALSE, conclusion="दाबी पूर्णतः भ्रामक र मिथ्या हो ।")
    verdict, source = resolve_verdict(b, "भ्रामक")
    assert source == "conclusion_mixed"
    assert verdict == "भ्रामक"
    # not the badge either
    assert resolve_verdict(b, "मिथ्या") == ("भ्रामक", "conclusion_mixed")


def test_claim_sentence_decides_a_mixed_conclusion():
    # Real pattern (harka-sampang 155384): the claim sentence says मिथ्या,
    # भ्रामक appears only in a general remark
    from scrapers.techpana import resolve_verdict
    b = body(conclusion="हर्क साम्पाङले पोस्ट गरेको दाबी मिथ्या हो । यस्ता भ्रामक पोस्टबाट सचेत रहनुहोस् ।")
    assert resolve_verdict(b, "भ्रामक") == ("मिथ्या", "conclusion_claim")
    b = body(conclusion="भाइरल भिडिओ पूर्ण रूपमा मिथ्या र भ्रामक छ ।")   # no दाबी sentence
    assert resolve_verdict(b, "मिथ्या") == ("भ्रामक", "conclusion_mixed")


def test_mixed_conclusion_without_usable_fallback_still_maps():
    from scrapers.techpana import resolve_verdict
    from pipeline.label_mapper import map_verdict
    b = body(conclusion="दाबी भ्रामक र मिथ्या हो ।")
    verdict, source = resolve_verdict(b, "")
    assert source == "conclusion_mixed"
    assert map_verdict(verdict)[1] == "FALSE_MISLEADING"


def test_summary_used_when_conclusion_names_nothing():
    from scrapers.techpana import resolve_verdict
    b = body(summary=FINDING_MISLEADING, conclusion="भिडिओ पुरानो हो ।")
    assert resolve_verdict(b, "मिथ्या") == ("भ्रामक", "summary")


def test_summary_used_when_no_conclusion_heading():
    from scrapers.techpana import resolve_verdict
    b = body(summary=FINDING_FALSE, conclusion=None)
    assert resolve_verdict(b, "भ्रामक") == ("मिथ्या", "summary")


def test_summary_ignores_sentences_without_a_finding_cue():
    # "भ्रामक" in a sentence that is not the desk's finding does not count
    from scrapers.techpana import resolve_verdict
    b = body(summary="केही मानिसले यसलाई भ्रामक भनेका छन् ।", conclusion=None)
    assert resolve_verdict(b, "मिथ्या") == ("मिथ्या", "stored")


def test_stored_fallback_when_text_names_nothing():
    from scrapers.techpana import resolve_verdict
    b = body(summary="", conclusion="भिडिओ पुरानो हो ।")
    assert resolve_verdict(b, "अपुष्ट") == ("अपुष्ट", "stored")


def test_nothing_found():
    from scrapers.techpana import resolve_verdict
    assert resolve_verdict(body(), "") == ("", "stored")
    assert resolve_verdict("", "") == ("", "stored")


def test_extract_verdict_from_body_unchanged_contract():
    # Older callers: exactly one verdict in the conclusion, else None
    from scrapers.techpana import extract_verdict_from_body
    assert extract_verdict_from_body(body(conclusion="दाबी मिथ्या हो ।")) == "मिथ्या"
    assert extract_verdict_from_body(body(conclusion="भ्रामक र मिथ्या")) is None
    assert extract_verdict_from_body(body(conclusion=None)) is None


def test_every_label_source_is_documented():
    from scrapers.techpana import resolve_verdict  # noqa: F401
    assert set(LABEL_SOURCES) == {
        "nfc_header", "conclusion", "conclusion_claim", "conclusion_mixed", "summary", "stored",
        "hand_checked"}   # 2.0: set only from data_validation/reference_labels.csv


# -----------------------------------------------------------------------------
# The scraper itself uses the same rule (no network: fetch_page is replaced)
# -----------------------------------------------------------------------------

def _page(og_image, body_text):
    paragraphs = "".join(f"<p>{line}</p>" for line in body_text.split("\n") if line)
    return (
        "<html><head>"
        f'<meta property="og:image" content="https://techpana.com/img/{og_image}">'
        "</head><body><h1>फ्याक्टचेक: भाइरल दाबी</h1>"
        f'<div class="article-content">{paragraphs}</div>'
        "</body></html>"
    )


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_scraper_reads_conclusion_before_badge(monkeypatch):
    from scrapers.techpana import TechpanaScraper
    scraper = TechpanaScraper()
    html = _page("Misleading_badge.jpg",
                 body(conclusion="भाइरल भिडिओ एआई निर्मित हो । दाबी मिथ्या हो ।"))
    monkeypatch.setattr(scraper, "fetch_page", lambda url: html)
    article = scraper.scrape_article("https://techpana.com/2026/159798/slug")
    assert article is not None
    assert article.raw_verdict_text == "मिथ्या"     # was "भ्रामक" (badge first)


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_scraper_falls_back_to_badge(monkeypatch):
    from scrapers.techpana import TechpanaScraper
    scraper = TechpanaScraper()
    html = _page("Misleading_badge.jpg", body(conclusion="भिडिओ पुरानो हो ।"))
    monkeypatch.setattr(scraper, "fetch_page", lambda url: html)
    article = scraper.scrape_article("https://techpana.com/2026/159798/slug")
    assert article.raw_verdict_text == "भ्रामक"


# -----------------------------------------------------------------------------
# On the committed data
# -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def by_url(normalized):
    return {e.source_url: e for e in normalized}


@pytest.mark.data
def test_every_record_has_a_valid_label_source(normalized):
    bad = [(e.source_url, e.label_source) for e in normalized
           if e.label_source not in LABEL_SOURCES]
    assert not bad, bad[:10]


@pytest.mark.data
def test_label_source_per_source(normalized):
    nfc = {e.label_source for e in normalized if e.source_name == "nepalfactcheck"}
    tp = {e.label_source for e in normalized if e.source_name == "techpana"}
    assert nfc <= {"nfc_header", "stored"}
    assert tp <= {"conclusion", "conclusion_claim", "conclusion_mixed", "summary", "stored"}


@pytest.mark.data
@pytest.mark.parametrize(
    "url, label_source, label_text",
    [
        # stored भ्रामक (badge), conclusion "दाबी मिथ्या हो"
        ("https://techpana.com/2026/159798/rabi-lamichhane-fake-ai-video-claims-igp-dan-bahadur-karki-dismissed",
         "conclusion", "FALSE_MISLEADING"),
        # stored भ्रामक, conclusion says साँचो/सही: REAL
        ("https://techpana.com/2026/159240/fact-check-harka-sampang-first-wife-divorce-property-case",
         "conclusion", "REAL"),
        # "दाबी पूर्णतः भ्रामक र मिथ्या हो"
        ("https://techpana.com/2026/159019/swornim-wagle-statue-viral-image-ai-generated-fact-check",
         "conclusion_mixed", "FALSE_MISLEADING"),
        # no verdict word in the conclusion; summary "दाबी भ्रामक"; stored अपुष्ट
        ("https://techpana.com/2025/149828/techpana-factcheck-mustang-uranium-claim-false",
         "summary", "FALSE_MISLEADING"),
        # conclusion names अपुष्ट and भ्रामक; summary "अपुष्ट"; stored मिथ्या
        ("https://techpana.com/2025/151229/misleading-qatar-death-penalty-video-viral-in-nepal",
         "summary", "UNVERIFIED"),
    ],
)
def test_known_articles(by_url, url, label_source, label_text):
    e = by_url[url]
    assert (e.label_source, e.verdict_label_text) == (label_source, label_text)


# Raw files written by the fixed scraper: what it stored must be what the
# normalizer would choose. (Vacuous until the first scrape after the fix.)
# Raw is never rewritten, so a file only has to agree with the rule that was
# in force when it was scraped: the गलत-by-context and claim-sentence rules
# (28 Nov 2026) apply to files scraped after 2026-11-28.
FIRST_FIXED_SCRAPE = "2026-11-29"


@pytest.mark.data
def test_new_raw_files_agree_with_normalizer():
    from scrapers.techpana import resolve_verdict
    disagree = []
    from utils.helpers import snapshot_files
    for path, _ in snapshot_files("raw/techpana"):
        if path.stem < FIRST_FIXED_SCRAPE:
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            stored = r.get("raw_verdict_text", "").strip()
            verdict, _ = resolve_verdict(r.get("body_text", "").strip(), stored)
            if verdict != stored:
                disagree.append((path.name, r["source_url"], stored, verdict))
    assert not disagree, disagree[:10]


# -----------------------------------------------------------------------------
# label_source plumbing (added in schema 1.1)
# -----------------------------------------------------------------------------

# (Schema version is checked in test_label_fine.py: 2.0 since fix 2.)


def test_label_source_round_trips():
    from schema.schema import NepFakeV2Example, to_dict, from_dict
    ex = NepFakeV2Example(
        example_id="NF2_20260825_0001", claim_text="दाबी", verdict_label=1,
        verdict_label_text="FALSE_MISLEADING", evidence_text="प्रमाण । " * 10,
        label_source="summary",
    )
    d = to_dict(ex)
    assert d["label_source"] == "summary"
    assert from_dict(d).label_source == "summary"


def test_validator_rejects_unknown_label_source():
    from tests.test_validator import make_valid_example
    from schema.validator import validate_example
    assert validate_example(make_valid_example(label_source="conclusion")).is_valid
    bad = validate_example(make_valid_example(label_source="badge"))
    assert not bad.is_valid
    assert any("label_source" in err for err in bad.errors)


def test_validator_allows_empty_label_source_with_warning():
    from tests.test_validator import make_valid_example
    from schema.validator import validate_example
    result = validate_example(make_valid_example())
    assert result.is_valid
    assert any("label_source" in w for w in result.warnings)


def test_stats_schema_version_not_hardcoded():
    from tests.test_validator import make_valid_example
    from pipeline.exporter import compute_stats
    stats = compute_stats([make_valid_example(label_source="conclusion")])
    assert stats["schema_version"] == SCHEMA_VERSION
    assert stats["label_source_distribution"]["conclusion"]["count"] == 1


@pytest.mark.parametrize("text, expected", [
    # "although the event is true, the video is misleading" (158844)
    ("घटना सत्य भए तापनि भाइरल भिडिओ भने एआई सिर्जित भ्रामक हो", {"भ्रामक"}),
    ("भिडिओ क्लिप सही भए पनि क्याप्सन भ्रामक छ", {"भ्रामक"}),
    ("सो कुरा सत्य हो", {"सही"}),                       # a plain "true" still counts
    ("दाबी असत्य भएको पुष्टि भएको छ", {"मिथ्या"}),      # असत्य is not "सत्य भए…"
])
def test_concession_is_not_a_verdict(text, expected):
    from scrapers.techpana import named_verdicts
    assert named_verdicts(text) == expected


def test_claim_sentence_decides_true_plus_false():
    # 155605: "… कुरा सत्य हो । तर, … भन्ने दाबी गलत हो ।"
    from scrapers.techpana import resolve_verdict
    b = body(conclusion="मतपेटिकामा सामान्य क्षति पुगेको कुरा सत्य हो । तर, ठुलो क्षति भएको भन्ने दाबी गलत हो ।")
    assert resolve_verdict(b, "") == ("मिथ्या", "conclusion_claim")
