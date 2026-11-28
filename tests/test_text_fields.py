"""
Test: model inputs without the answer (v2.0).

Brief items L1 (claim, not headline), L2 (evidence without verdict words),
the leakage gate, and the smaller text fields: language, date precision,
external links, NFC header line (B3), verdict word matching (B2).

The leakage gate is the important one. Before 2.0 a word counter (count
मिथ्या vs भ्रामक) scored 90% on evidence_text for the FALSE-vs-MISLEADING
task. After 2.0 it must do no better than always guessing the majority
class.
"""
import re

import pytest



def _rules():
    # imported lazily so this file still collects on code from before 2.0
    from pipeline import text_rules
    return text_rules


# -----------------------------------------------------------------------------
# Word rules
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("दाबी भ्रामक छ", True),
    ("यो मिथ्या सूचना हो", True),
    ("उनी भ्रमणमा गएका थिए", False),          # भ्रमण (travel) is not भ्रम
    ("तथ्यजाँचमा सही पुष्टि भयो", True),       # "true" inside a finding sentence
    ("उनले सही समयमा भाषण गरे", False),       # ordinary "right"
    ("The claim is misleading", True),
    ("तथ्य : सही सूचना ।", True),             # NFC's old fact box
])
def test_leaks_verdict(text, expected):
    assert _rules().leaks_verdict(text) is expected


@pytest.mark.parametrize("raw, fine", [
    ("सही होइन, भ्रामक", "MISLEADING"),       # negated TRUE ignored (B2)
    ("मिथ्या र भ्रामक", ""),                  # two verdicts: not one label
    ("भ्रमण", ""),                            # whole words only
    ("सत्य छैन", ""),
    ("यो दाबी मिथ्या हो", "FALSE"),
])
def test_map_verdict_fine_negation_and_whole_words(raw, fine):
    from pipeline.label_mapper import map_verdict, map_verdict_fine
    from config.settings import LABEL_FINE_TO_COARSE
    assert map_verdict_fine(raw) == fine
    assert map_verdict(raw)[0] == (LABEL_FINE_TO_COARSE[fine] if fine else -1)


# -----------------------------------------------------------------------------
# Cleaner and extractor on small made-up articles
# -----------------------------------------------------------------------------

TP_BODY = """फ्याक्टचेक: नेताले भाषण गरेको भन्दै भाइरल भिडिओ भ्रामक
लेखक
भदौ ९, २०८३
काठमाडौँ । सामाजिक सञ्जालमा नेताले सभामा भाषण गरेको दाबीसहित एउटा भिडिओ भाइरल भइरहेको छ ।
तर, टेकपाना फ्याक्टचेकले गरेको तथ्यजाँचमा उक्त दाबी भ्रामक पाइएको छ ।
दाबी
फेसबुक पेजले भिडिओ पोस्ट गरेको थियो । भिडिओ २०२२ को हो ।
निष्कर्ष
भिडिओ पुरानो हो, दाबी भ्रामक हो ।
प्रतिक्रिया
सम्बन्धित समाचार"""


def test_techpana_cleaner_removes_header_finding_and_conclusion():
    from pipeline.evidence_cleaner import clean_evidence
    ev, concl = clean_evidence("techpana", "फ्याक्टचेक: नेताले भाषण गरेको भन्दै भाइरल भिडिओ भ्रामक", TP_BODY)
    assert "भिडिओ २०२२ को हो" in ev
    assert not _rules().has_word(ev, _rules().VERDICT_WORDS)
    assert "लेखक" not in ev and "सम्बन्धित समाचार" not in ev
    assert "पुरानो" in concl and "निष्कर्ष" not in ev


def test_claim_is_the_lead_not_the_headline():
    from pipeline.evidence_cleaner import clean_evidence
    from pipeline.claim_extractor import extract_claim
    title = "फ्याक्टचेक: नेताले भाषण गरेको भन्दै भाइरल भिडिओ भ्रामक"
    ev, concl = clean_evidence("techpana", title, TP_BODY)
    claim, source = extract_claim("techpana", title, ev, concl)
    assert source == "lead"
    assert claim.startswith("सामाजिक सञ्जालमा नेताले सभामा भाषण")


def test_headline_fallback_strips_prefix_and_verdict():
    from pipeline.claim_extractor import clean_headline
    out = clean_headline("फ्याक्टचेक: नझुक्किनुस् ! नेताको भाइरल भिडिओ भ्रामक")
    assert out == "नेताको भाइरल भिडिओ"
    assert clean_headline("Fact Check: Old Video Is Misleading") == "Old Video"


# -----------------------------------------------------------------------------
# On the real data
# -----------------------------------------------------------------------------

@pytest.mark.data
def test_no_verdict_words_in_model_inputs(normalized):
    bad = [(e.source_url, f) for e in normalized for f in ("claim_text", "evidence_text")
           if _rules().text_leaks(getattr(e, f))]
    assert not bad, bad[:10]


@pytest.mark.data
def test_nfc_header_tag_not_in_evidence(normalized):
    tags = ("मिथ्या सूचना", "भ्रामक सूचना", "सही सूचना", "अपुष्ट सूचना")
    bad = [e.source_url for e in normalized
           if e.source_name == "nepalfactcheck" and any(t in e.evidence_text for t in tags)]
    assert not bad, bad[:10]


@pytest.mark.data
def test_leakage_gate_word_counter(normalized):
    # The cheat: count FALSE words vs MISLEADING words, guess the majority
    # class on a tie. On claim_text and evidence_text it must not beat the
    # majority baseline by more than 2 points.
    bench = [e for e in normalized if e.in_main_benchmark]
    majority = max(("FALSE", "MISLEADING"), key=lambda l: sum(e.label_fine == l for e in bench))
    base = sum(e.label_fine == majority for e in bench) / len(bench)

    def cheat(text):
        f = len(re.findall("मिथ्या|झुटो|असत्य", text))
        m = len(re.findall("भ्रामक|भ्रम|गलत", text))
        return "FALSE" if f > m else "MISLEADING" if m > f else majority

    for field in ("claim_text", "evidence_text"):
        acc = sum(cheat(getattr(e, field)) == e.label_fine for e in bench) / len(bench)
        assert acc <= base + 0.02, f"{field}: word counter {acc:.3f} vs majority {base:.3f}"


def test_generic_lead_takes_the_next_sentence():
    from pipeline.claim_extractor import extract_claim
    ev = ("बिहीबारदेखि सामाजिक सञ्जालमा एक भिडिओ भाइरल भइरहेको छ । "
          "भिडिओमा प्रधानमन्त्रीले संसद भवनमा नाच्दै गरेको देखाइएको छ ।\nदाबी\nअरू")
    claim, source = extract_claim("techpana", "शीर्षक", ev, "")
    assert source == "lead" and "प्रधानमन्त्रीले संसद भवनमा" in claim


@pytest.mark.data
def test_no_generic_claims(normalized):
    from pipeline.claim_extractor import is_generic
    bad = [(e.source_url, e.claim_text) for e in normalized
           if e.claim_source != "headline" and is_generic(e.claim_text)]
    assert not bad, bad[:5]


@pytest.mark.data
def test_claims_mostly_from_the_article(normalized):
    from config.settings import CLAIM_SOURCES
    assert {e.claim_source for e in normalized} <= set(CLAIM_SOURCES)
    from_headline = sum(e.claim_source == "headline" for e in normalized)
    assert from_headline <= 0.15 * len(normalized), from_headline


@pytest.mark.data
def test_evidence_not_empty_and_shorter_than_body(normalized):
    short = [e.source_url for e in normalized if len(e.evidence_text) < 200]
    assert len(short) <= 0.02 * len(normalized), short[:10]


@pytest.mark.data
def test_headline_and_conclusion_kept(normalized):
    assert all(e.headline for e in normalized)
    tp = [e for e in normalized if e.source_name == "techpana"]
    assert sum(bool(e.conclusion_text) for e in tp) >= 0.8 * len(tp)


@pytest.mark.data
def test_language_and_flag(normalized):
    assert {e.language for e in normalized} <= {"ne", "en"}
    assert all(e.is_native_nepali == (e.language == "ne") for e in normalized)
    assert not [e for e in normalized if e.language == "en" and e.in_main_benchmark]


@pytest.mark.data
def test_date_precision_and_order(normalized):
    assert {e.date_precision for e in normalized} <= {"day", "month", "year"}
    bad = [e.source_url for e in normalized if e.date_published > e.date_scraped]
    assert not bad, bad[:10]


def test_date_precision_values():
    from pipeline.normalizer import normalize_date_with_precision as f
    assert f("2026-07-14T14:47:19+05:45") == ("2026-07-14", "day")
    assert f("2026-08") == ("2026-08-01", "month")
    assert f("2026") == ("2026-01-01", "year")
    assert f("") == ("", "")


def test_external_links_drop_share_buttons_and_own_accounts():
    from pipeline.normalizer import filter_external_links
    links = ["https://www.facebook.com/TechPanaNews/", "https://x.com/techpananp",
             "https://www.linkedin.com/in/cmrnepal", "https://twitter.com/nepalfactcheck",
             "https://www.facebook.com/sharer/sharer.php?u=x",
             "https://techpana.com/2026/1/other", "https://www.facebook.com/reel/hashtag/?q=x",
             "https://archive.ph/abc12", "https://www.facebook.com/share/r/1FL2d3hSP2/",
             "https://archive.ph/abc12"]
    assert filter_external_links(links, "https://techpana.com/2026/1/a") == [
        "https://archive.ph/abc12", "https://www.facebook.com/share/r/1FL2d3hSP2/"]


@pytest.mark.data
def test_no_outlet_accounts_in_links(normalized):
    # the outlet's own Facebook / X / LinkedIn / YouTube accounts
    from urllib.parse import urlparse
    def first_segments(u):
        return " ".join(urlparse(u.lower()).path.strip("/").split("/")[:2])
    bad = [(e.source_url, u) for e in normalized for u in e.external_evidence_urls
           if any(a in first_segments(u) for a in ("techpana", "nepalfactcheck", "cmrnepal"))]
    assert not bad, bad[:5]


@pytest.mark.data
def test_no_self_links_in_data(normalized):
    # (an archive link of another outlet's article is fine: host only)
    from urllib.parse import urlparse
    own = {"techpana": "techpana.com", "nepalfactcheck": "nepalfactcheck.org"}
    bad = [(e.source_url, u) for e in normalized for u in e.external_evidence_urls
           if urlparse(u).netloc.lower().removeprefix("www.") == own[e.source_name]]
    assert not bad, bad[:5]


def test_nfc_header_line_found_by_title():
    # B3: the tag line is the line above the title, not a fixed line number
    from scrapers.nepalfactcheck import extract_verdict_from_header, is_explainer
    body = "☰\n×\nनयाँ मेनु\nभ्रामक सूचना\nशीर्षक यहाँ\nHome"
    assert extract_verdict_from_header(body, "शीर्षक यहाँ") == "भ्रामक सूचना"
    assert not is_explainer(body, "शीर्षक यहाँ")
    assert is_explainer("☰\n×\nएक्सप्लेनर\nशीर्षक", "शीर्षक")


def test_nfc_factcheck_explainer_hybrid_is_kept():
    # Tag line "तथ्यजाँच   एक्सप्लेनर   मिथ्या सूचना" (first seen 23 Nov 2026):
    # a fact-check with a verdict, not a pure explainer.
    from scrapers.nepalfactcheck import extract_verdict_from_header, is_explainer
    title = "नेताको अनुहार, एआईको बोली"
    hybrid = f"☰\n×\nतथ्यजाँच   एक्सप्लेनर   मिथ्या सूचना\n{title}\nHome"
    assert not is_explainer(hybrid, title)
    assert extract_verdict_from_header(hybrid, title) == "मिथ्या सूचना"
    pure = f"☰\n×\nएक्सप्लेनर   जलवायु र वातावरण   सही सूचना\n{title}\nHome"
    assert is_explainer(pure, title)
    tag_first = f"☰\n×\nजलवायु र वातावरण   एक्सप्लेनर   सही सूचना\n{title}\nHome"
    assert is_explainer(tag_first, title)


@pytest.mark.data
def test_no_verdict_tag_word_in_benchmark_evidence(normalized):
    # Zero, not "few": any word starting with मिथ्या / भ्रामक / अपुष्ट (and
    # the whole words झुटो, असत्य) in a benchmark evidence_text is a leak.
    # Before 28 Nov 2026 the danda in "तथ्य : भ्रामक।" hid 14 of them.
    stems = re.compile(r"(?<![ऀ-ॣॱ-ॿ])(?:मिथ्या|भ्रामक|अपुष्ट)"
                       r"|(?<![ऀ-ॣॱ-ॿ])(?:झुटो|झूटो|असत्य)(?![ऀ-ॣॱ-ॿ])")
    bad = [(e.example_id, stems.search(e.evidence_text).group(0))
           for e in normalized if e.in_main_benchmark and stems.search(e.evidence_text)]
    assert not bad, bad[:10]


def test_evidence_has_no_links_or_outlet_name():
    # 28 Nov 2026: NFC upload links were a label shortcut (26% of MISLEADING
    # vs 13% of FALSE rows); the outlet naming itself gives away the source.
    from pipeline.evidence_cleaner import mask_shortcuts
    t = mask_shortcuts("टेकपाना फ्याक्टचेक डेस्कले जाँच गर्‍यो । हेर्नुहोस् "
                       "https://nepalfactcheck.org/wp-content/uploads/2026/11/x.mp4 भिडिओ । "
                       "नेपाल फ्याक्टचेकले पनि । निष्कर्ष:")
    assert "http" not in t and "टेकपाना" not in t and "नेपाल फ्याक्टचेक" not in t
    assert t.count("[OUTLET]") == 2 and not t.endswith("निष्कर्ष:")


@pytest.mark.data
def test_committed_evidence_has_no_links_or_outlet_name():
    import pandas as pd
    d = pd.read_csv("data/nepfakev2.csv", keep_default_na=False)
    bad = d[d["evidence_text"].str.contains(r"https?://|टेकपाना|नेपाल\s*फ्याक्ट\s*चेक|नेपालफ्याक्टचेक",
                                            regex=True)]
    assert bad.empty, bad["source_url"].head().tolist()
