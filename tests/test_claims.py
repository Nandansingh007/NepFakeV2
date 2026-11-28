"""
Test: where claim_text comes from (claim fix, 28 Nov 2026).

  - NFC summary box "दावी : …" (both spellings, ":" or "ः"), last box wins,
    rejected if it states the verdict or the finding
  - claimant from "दावीकर्ता : …"
  - NFC "के … हो?" headline
  - TechPana: the post's caption quoted in the "दाबी" section
  - data_validation/claims_reference.csv: only checked rows count, a claim
    with a verdict word is refused, the override sets claim_source
    "hand_checked"
  - claim groups do not move when a person rewrites claim_text
"""
import pytest

NFC_BODY = (
    "तथ्यजाँच\nभ्रामक सूचना\nशीर्षक\n…\nलेखको मुख्य भाग।\n"
    "तथ्य जाँच\n"
    "दावी :\nकाठमाडौँको सुकुम्बासी बस्ती बाढीले बगाएको भन्ने दावीसहितको भिडियो।\n"
    "दावीकर्ता :\nसामाजिक सञ्जाल प्रयोगकर्ता (केजी रोकाया फेसबुक पेज)।\n"
    "तथ्यः\nभ्रामक सूचना। उक्त भिडियो इन्डोनेसियाको हो।\n"
    "प्रतिक्रिया दिनुहोस्\n"
)

TP_BODY = (
    "काठमाडौँ । सामाजिक सञ्जालमा एउटा भिडिओ भाइरल भइरहेको छ ।\n"
    "तर, टेकपानाको फ्याक्टचेकले भिडिओ पुरानो भएको फेला पारेको छ ।\n"
    "दाबी\n"
    "फेसबुकमा ‘राम’ नामका प्रयोगकर्ताले एउटा भिडिओ पोस्ट गरेका छन् । "
    "उक्त भिडिओको क्याप्सनमा ‘मन्त्रीले आज संसदमा सबै सांसदलाई धम्की दिए हेर्नुहोस् यो भिडिओ’ लेखिएको छ ।\n"
    "तथ्य\n"
    "भिडिओ दुई वर्ष पुरानो हो ।\n"
)


def _ce():
    from pipeline import claim_extractor
    return claim_extractor


# -----------------------------------------------------------------------------
# Rules
# -----------------------------------------------------------------------------

def test_nfc_box_is_the_claim():
    claim, source = _ce().extract_claim("nepalfactcheck", "शीर्षक", "", "", NFC_BODY)
    assert source == "claim_box"
    assert claim == "काठमाडौँको सुकुम्बासी बस्ती बाढीले बगाएको भन्ने दावीसहितको भिडियो"


@pytest.mark.parametrize("label", ["दावी :", "दाबी :", "दावी:", "दाबी ः", "दावी :\n"])
def test_nfc_box_spellings(label):
    body = f"अरू\n{label} नेताले संसदमा नयाँ कानुन ल्याउने घोषणा गरे\nदावीकर्ता : एक पत्रिका\nतथ्य : भ्रामक"
    assert _ce().nfc_claim_box(body) == "नेताले संसदमा नयाँ कानुन ल्याउने घोषणा गरे"


def test_nfc_last_box_wins():
    body = ("दावी : पुरानो लेखको दाबी यहाँ उल्लेख गरिएको थियो\nतथ्य : x\n"
            "बीचको पाठ\n"
            "दावी : यो लेखको आफ्नै दाबी हो जुन जाँच गरियो\nदावीकर्ता : क\nतथ्य : y")
    assert _ce().nfc_claim_box(body) == "यो लेखको आफ्नै दाबी हो जुन जाँच गरियो"


@pytest.mark.parametrize("bad", [
    "यो भिडियो पुरानो हो भने कुरा सामाजिक सञ्जालमा फैलियो",   # finding word
    "नेताले भाषण गरेको भ्रामक भिडियो सामाजिक सञ्जालमा",       # verdict word
    "भाइरल भिडियो",                                          # too short / generic
])
def test_nfc_box_rejected_when_it_gives_the_answer(bad):
    body = f"दावी : {bad}\nदावीकर्ता : क\nतथ्य : z"
    claim, source = _ce().extract_claim("nepalfactcheck", "शीर्षक", "", "", body)
    assert source != "claim_box"


def test_nfc_claimant():
    assert _ce().extract_claimant("nepalfactcheck", NFC_BODY) == \
        "सामाजिक सञ्जाल प्रयोगकर्ता (केजी रोकाया फेसबुक पेज)"
    assert _ce().extract_claimant("techpana", NFC_BODY) == ""


def test_nfc_question_headline():
    title = "के मास्क लगाउँदा तपाईँको अक्सिजन लेभल घट्छ?"
    claim, source = _ce().extract_claim("nepalfactcheck", title, "", "", "कुनै बाकस छैन")
    assert (claim, source) == ("के मास्क लगाउँदा तपाईँको अक्सिजन लेभल घट्छ", "headline_question")
    # not a question, or not starting with के: no
    assert _ce().headline_question("मास्कबारे भाइरल दाबी") == ""


def test_tp_caption_is_the_claim():
    claim, source = _ce().extract_claim("techpana", "फ्याक्टचेक: शीर्षक", "", "", TP_BODY)
    assert source == "claim_caption"
    assert claim == "मन्त्रीले आज संसदमा सबै सांसदलाई धम्की दिए हेर्नुहोस् यो भिडिओ"


def test_tp_caption_needs_a_cue_and_eight_words():
    short = TP_BODY.replace("मन्त्रीले आज संसदमा सबै सांसदलाई धम्की दिए हेर्नुहोस् यो भिडिओ", "राम श्याम")
    assert _ce().tp_caption(short) == ""
    no_cue = ("x\nदाबी\nउनले ‘मन्त्रीले आज संसदमा सबै सांसदलाई धम्की दिए हेर्नुहोस् यो भिडिओ’ "
              "भनेर कराए ।\nतथ्य\ny")
    assert _ce().tp_caption(no_cue) == ""


def test_tp_quote_after_the_claim_section_is_ignored():
    # quotes under "तथ्य" are the fact-checker's, not the claim
    body = ("x\nदाबी\nएउटा पोस्ट भाइरल छ ।\nतथ्य\n"
            "प्रवक्ताले ‘यो भिडिओ हाम्रो कार्यक्रमको होइन र यो कुरा गलत हो भनेर लेखिएको छ’ लेखिएको छ ।")
    assert _ce().tp_caption(body) == ""


# -----------------------------------------------------------------------------
# Hand-checked claims
# -----------------------------------------------------------------------------

def _write(tmp_path, rows):
    p = tmp_path / "claims.csv"
    lines = ["source_url,claim_text,claimant,checked,note"] + rows
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def test_missing_claims_file_changes_nothing(tmp_path):
    from pipeline.claims_reference import load_claims
    assert load_claims(tmp_path / "nope.csv") == {}


def test_only_checked_rows_count(tmp_path):
    from pipeline.claims_reference import load_claims
    p = _write(tmp_path, [
        "https://techpana.com/2026/1/a,मन्त्रीले संसदमा सांसदलाई धम्की दिए,राम,y,",
        "https://techpana.com/2026/2/b,यो पङ्क्ति अझै जाँच भएको छैन,,,",
        "https://techpana.com/2026/3/c,,,y,",
    ])
    out = load_claims(p)
    assert list(out) == ["https://techpana.com/2026/1/a"]
    assert out["https://techpana.com/2026/1/a"] == {
        "claim_text": "मन्त्रीले संसदमा सांसदलाई धम्की दिए", "claimant": "राम",
        "claim_platform": ""}


def test_claim_with_verdict_word_is_refused(tmp_path):
    from pipeline.claims_reference import load_claims
    p = _write(tmp_path, ["https://techpana.com/2026/1/a,मन्त्रीको भिडिओ भ्रामक हो,,y,"])
    with pytest.raises(ValueError, match="verdict"):
        load_claims(p)


def test_override_sets_hand_checked():
    from pipeline.normalizer import normalize_article
    raw = {"source_name": "techpana",
           "source_url": "https://techpana.com/2026/159999/test",
           "title": "फ्याक्टचेक: मन्त्रीको भिडिओ भ्रामक", "body_text": TP_BODY + "\nनिष्कर्ष\nभ्रामक\n",
           "raw_verdict_text": "भ्रामक", "date_published": "2026-01-05"}
    plain = normalize_article(dict(raw))
    if plain is None:
        pytest.skip("test article not recognised as a TechPana fact-check")
    hand = {"https://techpana.com/2026/159999/test":
            {"claim_text": "मन्त्रीले संसदमा सांसदलाई धम्की दिए", "claimant": "राम"}}
    ex = normalize_article(dict(raw), claims=hand)
    assert (ex.claim_text, ex.claim_source, ex.claimant) == \
        ("मन्त्रीले संसदमा सांसदलाई धम्की दिए", "hand_checked", "राम")
    assert plain.claim_source != "hand_checked"


# -----------------------------------------------------------------------------
# On the real data
# -----------------------------------------------------------------------------

@pytest.mark.data
def test_most_nfc_claims_come_from_the_box(normalized):
    nfc = [e for e in normalized if e.source_name == "nepalfactcheck" and e.in_main_benchmark]
    box = sum(e.claim_source == "claim_box" for e in nfc)
    assert box >= 0.75 * len(nfc), f"{box} of {len(nfc)}"


@pytest.mark.data
def test_no_finding_words_in_box_claims(normalized):
    from pipeline.claim_extractor import FINDING_WORDS
    from pipeline.text_rules import has_word
    bad = [(e.source_url, e.claim_text) for e in normalized
           if e.claim_source == "claim_box" and has_word(e.claim_text, FINDING_WORDS)]
    assert not bad, bad[:5]


@pytest.mark.data
def test_groups_do_not_move_when_a_claim_is_rewritten(normalized):
    import copy
    from pipeline.claim_groups import find_groups
    rows = [e for e in normalized if e.in_main_benchmark]
    before = find_groups(rows)
    rewritten = copy.deepcopy(rows)
    for e in rewritten:
        if e.source_name == "techpana":
            e.claim_text = "एक व्यक्तिले हातले लेखेको पूर्ण रूपमा नयाँ दाबी"
    assert find_groups(rewritten) == before


@pytest.mark.parametrize("fact_line", ["तथ्य :", "तथ्यः", "तथ्य/निष्कर्ष :", "तथ्य/निश्कर्ष :",
                                       "तथ्य जाँच :", "तथ्यजाँच :", "निष्कर्ष :", "निश्कर्ष:"])
def test_nfc_claimant_before_any_fact_line(fact_line):
    body = f"दावी :\nनेताले नयाँ कानुन ल्याउने घोषणा गरे\nदावीकर्ता :\nराम नामक फेसबुक पेज।\n{fact_line} भ्रामक"
    assert _ce().nfc_claimant(body) == "राम नामक फेसबुक पेज"


# -----------------------------------------------------------------------------
# claim_platform, verified tier, --gold scoring
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("राम नामक फेसबुक पेज", "facebook"),
    ("टिकटक प्रयोगकर्ता @abc र एक्स प्रयोगकर्ता सुमन", "tiktok|x"),
    ("रातोपाटी डटकम, लोकान्तर डटकम", "news_media"),
    ("एक्सप्लेनर लेख", ""),                       # एक्स inside a word is not X
    ("सामाजिक सञ्जाल प्रयोगकर्ता", ""),
])
def test_find_platforms(text, expected):
    assert _ce().find_platforms(text) == expected


def test_tp_platform_from_the_claim_section():
    body = "x\nदाबी\nफेसबुकमा ‘राम’ नामका प्रयोगकर्ताले भिडिओ पोस्ट गरेका छन् ।\nतथ्य\ny"
    assert _ce().extract_platform("techpana", "", body) == "facebook"


def test_hand_platform_is_checked(tmp_path):
    from pipeline.claims_reference import load_claims
    p = tmp_path / "c.csv"
    p.write_text("source_url,claim_text,claim_platform,checked\n"
                 "https://techpana.com/2026/1/a,मन्त्रीले संसदमा सांसदलाई धम्की दिए,TikTok | facebook,y\n",
                 encoding="utf-8")
    assert load_claims(p)["https://techpana.com/2026/1/a"]["claim_platform"] == "facebook|tiktok"
    p.write_text("source_url,claim_text,claim_platform,checked\n"
                 "https://techpana.com/2026/1/a,मन्त्रीले संसदमा सांसदलाई धम्की दिए,myspace,y\n",
                 encoding="utf-8")
    with pytest.raises(ValueError, match="claim_platform"):
        load_claims(p)


def test_verified_gold_only_when_label_hand_checked():
    from pipeline.normalizer import normalize_article
    raw = {"source_name": "techpana",
           "source_url": "https://techpana.com/2026/159999/test",
           "title": "फ्याक्टचेक: मन्त्रीको भिडिओ भ्रामक", "body_text": TP_BODY + "\nनिष्कर्ष\nभ्रामक\n",
           "raw_verdict_text": "भ्रामक", "date_published": "2026-01-05"}
    plain = normalize_article(dict(raw))
    if plain is None:
        pytest.skip("test article not recognised as a TechPana fact-check")
    assert plain.verified == "silver"
    gold = normalize_article(dict(raw), references={"https://techpana.com/2026/159999/test": "FALSE"})
    assert (gold.verified, gold.label_source, gold.label_fine) == ("gold", "hand_checked", "FALSE")


@pytest.mark.data
def test_every_row_has_a_tier(normalized):
    assert {e.verified for e in normalized} <= {"gold", "silver"}
    assert all((e.verified == "gold") == (e.label_source == "hand_checked") for e in normalized)


def test_evaluate_gold_only(tmp_path):
    from pipeline import evaluate
    rel = tmp_path / "v2.0"
    rel.mkdir()
    (rel / "test.csv").write_text(
        "example_id,label_fine,verified\n"
        "a,FALSE,gold\nb,MISLEADING,gold\nc,FALSE,silver\nd,MISLEADING,silver\n", encoding="utf-8")
    pred = tmp_path / "p.csv"
    pred.write_text("example_id,prediction\na,FALSE\nb,MISLEADING\nc,MISLEADING\nd,FALSE\n",
                    encoding="utf-8")
    assert evaluate.main([str(pred), "--release-dir", str(rel), "--gold"]) == 0
    gold = {"a": "FALSE", "b": "MISLEADING"}
    assert evaluate.scores(gold, {"a": "FALSE", "b": "MISLEADING"})["macro_f1"] == 1.0
    # all rows: c and d are wrong, so the plain score is lower
    full = evaluate._read(rel / "test.csv", "label_fine")
    assert evaluate.scores(full, evaluate._read(pred, "prediction"))["macro_f1"] == 0.5
