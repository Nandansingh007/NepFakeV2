"""
Test: the fine label (Phase 1, fix 2, schema 2.0).

label_fine splits the coarse FALSE_MISLEADING label:
    FALSE       मिथ्या (and झुटो, असत्य)
    MISLEADING  भ्रामक (and भ्रम, "गलत सन्दर्भ/अर्थ")
    TRUE        सही (and साँचो, सत्य)
    UNVERIFIED  अपुष्ट
There is no MIXED label (28 Nov 2026): a TechPana conclusion naming both
takes its claim sentence's verdict, else MISLEADING (label_source
conclusion_claim / conclusion_mixed).
The coarse label (verdict_label / verdict_label_text) is kept unchanged.

in_main_benchmark marks rows for the main task (FALSE vs MISLEADING):
label_fine is FALSE or MISLEADING, the verdict was read from the text
(label_source is not in BENCHMARK_EXCLUDED_SOURCES), and the article is in
Nepali (language "ne").
"""
import pytest

from config import settings

# Read lazily so this file still collects (and fails test by test) on code
# from before the fix.
LABELS_FINE = getattr(settings, "LABELS_FINE", {})
FINE_TO_COARSE = getattr(settings, "LABEL_FINE_TO_COARSE", {})
EXCLUDED = getattr(settings, "BENCHMARK_EXCLUDED_SOURCES", None)


# -----------------------------------------------------------------------------
# Definitions
# -----------------------------------------------------------------------------

def test_schema_version_is_2_0():
    assert settings.SCHEMA_VERSION == "2.0"


def test_fine_labels_defined():
    assert set(LABELS_FINE) == {"FALSE", "MISLEADING", "TRUE", "UNVERIFIED"}


def test_fine_to_coarse():
    assert FINE_TO_COARSE == {
        "FALSE": 1, "MISLEADING": 1, "TRUE": 0, "UNVERIFIED": 2}


def test_benchmark_excludes_only_stored():
    # Decision 22 Nov 2026: stored (badge-only) rows stay out until hand-checked.
    # 28 Nov 2026: conclusion_mixed rows are MISLEADING and in the benchmark.
    assert EXCLUDED == {"stored"}


# -----------------------------------------------------------------------------
# map_verdict_fine
# -----------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("मिथ्या", "FALSE"), ("मिथ्या सूचना", "FALSE"), ("झुटो", "FALSE"), ("असत्य", "FALSE"),
        ("भ्रामक", "MISLEADING"), ("भ्रामक सूचना", "MISLEADING"), ("भ्रम", "MISLEADING"),
        ("गलत", "MISLEADING"),
        ("सही", "TRUE"), ("सही सूचना", "TRUE"), ("साँचो", "TRUE"), ("सत्य", "TRUE"),
        ("अपुष्ट", "UNVERIFIED"), ("अपुष्ट सूचना", "UNVERIFIED"),
        ("", ""), ("कुनै अर्को शब्द", ""),
    ],
)
def test_map_verdict_fine(raw, expected):
    from pipeline.label_mapper import map_verdict_fine
    assert map_verdict_fine(raw) == expected


def test_fine_and_coarse_agree_for_every_mapped_word():
    # Every verdict word must give the same coarse label both ways
    from pipeline.label_mapper import VERDICT_MAP, map_verdict, map_verdict_fine
    bad = []
    for word in VERDICT_MAP:
        fine = map_verdict_fine(word)
        if FINE_TO_COARSE.get(fine) != map_verdict(word)[0]:
            bad.append((word, fine, map_verdict(word)))
    assert not bad, bad


# -----------------------------------------------------------------------------
# Schema + validator
# -----------------------------------------------------------------------------

def test_round_trip_label_fine_and_flag():
    from schema.schema import NepFakeV2Example, to_dict, from_dict
    ex = NepFakeV2Example(
        example_id="NF2_20260825_0001", claim_text="दाबी", verdict_label=1,
        verdict_label_text="FALSE_MISLEADING", evidence_text="प्रमाण । " * 10,
        label_fine="FALSE", in_main_benchmark=True,
    )
    d = to_dict(ex)
    assert d["label_fine"] == "FALSE"
    assert d["in_main_benchmark"] is True
    back = from_dict(d)
    assert back.label_fine == "FALSE" and back.in_main_benchmark is True


@pytest.mark.parametrize("text, expected", [
    ("True", True), ("False", False), ("true", True), ("0", False), ("", False),
    (True, True), (False, False)])
def test_from_dict_reads_csv_booleans(text, expected):
    # A CSV gives the string "False", which is truthy: it must read as False
    from schema.schema import from_dict
    d = dict(example_id="x", claim_text="x", verdict_label=1,
             verdict_label_text="FALSE_MISLEADING", evidence_text="x",
             external_evidence_urls="",
             in_main_benchmark=text)
    assert from_dict(d).in_main_benchmark is expected


def _example(**kw):
    from tests.test_validator import make_valid_example
    base = dict(label_source="conclusion", label_fine="FALSE", in_main_benchmark=True)
    base.update(kw)
    return make_valid_example(**base)


def test_validator_accepts_consistent_record():
    from schema.validator import validate_example
    r = validate_example(_example())
    assert r.is_valid, r.errors


@pytest.mark.parametrize("overrides, needle", [
    ({"label_fine": "WRONG"}, "label_fine invalid"),
    ({"label_fine": "TRUE"}, "label_fine"),                        # TRUE but coarse is 1
    ({"label_fine": "UNVERIFIED", "in_main_benchmark": True}, "in_main_benchmark"),
    ({"label_fine": "MIXED"}, "label_fine invalid"),               # label removed 28 Nov 2026
    ({"label_source": "stored"}, "in_main_benchmark"),
])
def test_validator_rejects_inconsistent_record(overrides, needle):
    from schema.validator import validate_example
    r = validate_example(_example(**overrides))
    assert not r.is_valid
    assert any(needle in e for e in r.errors), r.errors


def test_validator_allows_empty_label_fine_with_warning():
    from schema.validator import validate_example
    r = validate_example(_example(label_fine="", in_main_benchmark=False))
    assert r.is_valid, r.errors
    assert any("label_fine" in w for w in r.warnings)


def test_stats_have_fine_distribution():
    from pipeline.exporter import compute_stats
    stats = compute_stats([
        _example(),
        _example(label_fine="MISLEADING"),
        _example(label_fine="UNVERIFIED", verdict_label=2, in_main_benchmark=False),
    ])
    assert stats["schema_version"] == "2.0"
    assert stats["label_fine_distribution"]["FALSE"]["count"] == 1
    assert stats["label_fine_by_source"]["techpana"]["UNVERIFIED"] == 1
    assert stats["main_benchmark"] == {"total": 2, "FALSE": 1, "MISLEADING": 1}


# -----------------------------------------------------------------------------
# On the committed data
# -----------------------------------------------------------------------------

@pytest.mark.data
def test_every_record_has_a_consistent_fine_label(normalized):
    bad = [(e.source_url, e.label_fine, e.verdict_label) for e in normalized
           if e.label_fine not in LABELS_FINE
           or FINE_TO_COARSE[e.label_fine] != e.verdict_label]
    assert not bad, bad[:10]


@pytest.mark.data
def test_conclusion_mixed_is_misleading(normalized):
    # A verdict naming both मिथ्या and भ्रामक (claim sentence too) is MISLEADING
    bad = [(e.source_url, e.label_fine) for e in normalized
           if e.label_source == "conclusion_mixed" and e.label_fine != "MISLEADING"]
    assert not bad, bad[:10]
    assert not [e for e in normalized if e.label_fine == "MIXED"]


@pytest.mark.data
def test_main_benchmark_flag(normalized):
    bad = [e.source_url for e in normalized
           if e.in_main_benchmark != (
               e.label_fine in ("FALSE", "MISLEADING")
               and e.label_source not in EXCLUDED
               and e.language == "ne")]
    assert not bad, bad[:10]


@pytest.mark.data
def test_nfc_has_no_mixed(normalized):
    # NepalFactCheck gives one header tag, so it can never be MIXED
    assert not [e for e in normalized
                if e.source_name == "nepalfactcheck" and e.label_fine == "MIXED"]


@pytest.mark.data
@pytest.mark.parametrize("url, fine, in_bench", [
    # conclusion "दाबी मिथ्या हो" (badge said भ्रामक)
    ("https://techpana.com/2026/159798/rabi-lamichhane-fake-ai-video-claims-igp-dan-bahadur-karki-dismissed",
     "FALSE", True),
    # "दाबी पूर्णतः भ्रामक र मिथ्या हो": both, also in the claim sentence -> MISLEADING
    ("https://techpana.com/2026/159019/swornim-wagle-statue-viral-image-ai-generated-fact-check",
     "MISLEADING", True),
    # conclusion names both, but its claim sentence "… दाबी मिथ्या हो" -> FALSE
    ("https://techpana.com/2026/155384/harka-sampang-fake-x-account-viral-post-truth",
     "FALSE", True),
    # "दाबी गलत हो" -> FALSE (was MISLEADING before 28 Nov 2026)
    ("https://techpana.com/2026/155501/fact-check-okhaldhunga-ncp-joining-viral-photo-fake",
     "FALSE", True),
    # summary "दाबी भ्रामक"
    ("https://techpana.com/2025/149828/techpana-factcheck-mustang-uranium-claim-false",
     "MISLEADING", True),
    # UNVERIFIED: not part of the binary main task
    ("https://techpana.com/2025/151229/misleading-qatar-death-penalty-video-viral-in-nepal",
     "UNVERIFIED", False),
])
def test_known_articles_fine(normalized, url, fine, in_bench):
    e = {x.source_url: x for x in normalized}[url]
    assert (e.label_fine, e.in_main_benchmark) == (fine, in_bench)
