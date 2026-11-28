# pipeline/claim_extractor.py
# =============================================================================
# Brief item L1: the claim, not the fact-checker's headline.
#
# The headline gives the answer away ("... दाबी भ्रामक", "नझुक्किनुस्").
# Order (first that works wins; claim_source says which):
#   NepalFactCheck only:
#   1. "claim_box"   NFC's summary box near the end of the article:
#                        दावी : <claim>   (or दाबी, ":" or "ः")
#                        दावीकर्ता : <who made it>   -> claimant column
#                        तथ्य : <verdict and finding>
#                    In 85% of benchmark rows (nearly every article from
#                    2021 on). The last box in the body wins.
#   2. "headline_question"  an NFC headline "के … हो?" asks the claim
#                    without answering it: kept as written, minus the "?"
#   TechPana only:
#   1. "claim_caption" the post's own text, quoted in the "दाबी" section
#                    ("क्याप्सनमा ‘…’ लेखिएको छ"): first quote of 8+ words
#                    next to a caption cue
#   Both outlets, in this order, if the steps above found nothing:
#   2. "lead_quote"  the quoted claim inside the lead sentence:
#                    सामाजिक सञ्जालमा “<claim>” भन्दै भिडिओ भाइरल छ
#   3. "lead"        the lead sentence that reports the viral claim
#   4. "claim_section" the first sentence under the "दाबी" / "के हो दाबी ?" heading
#   5. "headline"    the headline with prefixes, verdict and cue words removed
# Every step except the last is rejected if it contains a verdict word, and
# the outlet-specific steps also if they contain a finding word (पुरानो,
# होइन, …: "the video is old" is the answer, not the claim).
#
# Hand-written claims in data_validation/claims_reference.csv override all
# of this (claim_source "hand_checked"; pipeline/claims_reference.py).
# Report the 50-claim hand check per claim_source.
# =============================================================================

import re

from pipeline.text_rules import (CUE_WORDS, FINDING_CUE, HEADLINE_PREFIX,
                                 VERDICT_WORDS, has_word, leaks_verdict,
                                 split_sentences)

QUOTE = re.compile(r"[“\"‘']([^“”\"‘’']{15,300})[”\"’']")
VIRAL = re.compile(r"भाइरल|दावी|सामाजिक\s*सञ्जाल|फैलि|फैलाइ|दाबी|शेयर|सेयर|पोस्ट|भनिएको|भन्दै")
DATELINE = re.compile(r"^\s*[\u0900-\u097F]{2,12}\s*।\s*")
CLAIM_HEADING = re.compile(r"\n\s*(?:के\s*(?:हो|छ)\s*)?(?:दाबी|दावी)\s*\??\s*\n")
EN_VERDICT = re.compile(r"\b(?:is\s+)?(?:fake|falsely|false|misleading(?:ly)?|unverified|fabricated|ai[\s-]generated)\b", re.I)

# NFC summary box. The claim runs up to the claimant or the fact line.
NFC_BOX = re.compile(
    r"(?:^|\n)\s*दा[वब]ी\s*[:ः]\s*(.{8,600}?)\s*\n\s*(?:दा[वब]ीकर्ता|(?:तथ्य\s*जाँ+च|तथ्य)(?:\s*/\s*नि[ष्श]्कर्ष)?|नि[ष्श]्कर्ष)\s*\n?\s*[:ः]",
    re.S)
NFC_CLAIMANT = re.compile(
    r"दा[वब]ीकर्ता\s*\n?\s*[:ः]\s*(.{2,300}?)\s*\n\s*(?:(?:तथ्य\s*जाँ+च|तथ्य)(?:\s*/\s*नि[ष्श]्कर्ष)?|नि[ष्श]्कर्ष)\s*\n?\s*[:ः]",
    re.S)
# TechPana "दाबी" section: from the heading to the "तथ्य" / "निष्कर्ष" heading
TP_CLAIM_HEADING = re.compile(r"\n\s*(?:के\s*(?:हो|छ)\s*)?दा[बव]ी\s*\??\s*\n")
TP_SECTION_END = re.compile(r"\n\s*(?:तथ्य|निष्कर्ष)\s*\n")
TP_QUOTE = re.compile(r"[“\"‘']\s*([^“”\"‘’']{20,600}?)\s*[”\"’']")
CAPTION_CUE = re.compile(r"क्याप्सन|लेखिएको|लेखिएका|लेखेका|लेखेको|भनिएको|भन्दै|उल्लेख|पोस्ट|भनेका|भनेको")
# Words that state the finding: fine in an article, wrong in a claim
FINDING_WORDS = ["पुरानो", "होइन", "हैन", "होइनन्", "छैन", "छैनन्", "नक्कली",
                 "फेक", "एडिटेड", "एडिट", "एआई-निर्मित", "एआई सिर्जित"]


GENERIC = set("""
सामाजिक सञ्जाल सञ्जालमा फेसबुक फेसबुकमा टिकटक युट्युब एक एउटा केही दिन दिनदेखि
दिनयता यता पछिल्ला पछिल्लो अहिले यतिबेला हिजोदेखि आजदेखि बिहीबारदेखि बुधबारदेखि
मङ्गलबारदेखि सोमबारदेखि आइतबारदेखि शनिबारदेखि शुक्रबारदेखि भिडिओ भिडियो तस्बिर
फोटो पोस्ट भाइरल भइरहेको भएको छ छन् हो गरिएको गर्दै भन्दै दाबी दावी सहित दाबीसहित
""".split())


def is_generic(sentence: str) -> bool:
    """A lead sentence that says only "a video is going viral"."""
    words = re.findall(r"[\u0900-\u097F]+|[A-Za-z]+", sentence or "")
    return len([w for w in words if w not in GENERIC]) < 4


def clean_headline(headline: str) -> str:
    """Headline minus prefixes, verdict words and cue words."""
    text = HEADLINE_PREFIX.sub("", headline or "")
    for w in VERDICT_WORDS + CUE_WORDS + ["दाबी", "दावी", "यसकारण", "तथ्य", "साँचो होइन", "होइन"]:
        text = re.sub(rf"(?<![ऀ-ॿ]){re.escape(w)}(?![ऀ-ॿ])", " ", text)
    text = EN_VERDICT.sub(" ", text)
    text = re.sub(r"\s*[,;:ः!|]\s*(?=[,;:ः!|]|$)", " ", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;:ः!?|-–—")


def _lead_sentences(evidence_lead: str) -> list[str]:
    out = []
    for s in split_sentences(evidence_lead.replace("\xa0", " "))[:5]:
        s = DATELINE.sub("", s).strip()
        if len(s) < 15:
            continue    # the dateline "काठमाडौँ ।" on its own
        if FINDING_CUE.search(s) or s.startswith("तर"):
            break       # the finding sentence ends the claim part of the lead
        out.append(s)
    return out


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def _usable(claim: str, min_words: int = 3) -> bool:
    """A claim from an outlet-specific step: long enough, no verdict word,
    no finding word."""
    return (len(claim) >= 15 and len(claim.split()) >= min_words
            and not is_generic(claim)
            and not leaks_verdict(claim) and not has_word(claim, FINDING_WORDS))


def nfc_claim_box(text: str) -> str:
    """The claim from NFC's summary box ("" if there is none). Last box wins:
    an earlier one can belong to a related article quoted in the body."""
    boxes = list(NFC_BOX.finditer("\n" + (text or "")))
    if not boxes:
        return ""
    return _flat(boxes[-1].group(1)).strip(" ‘’“”\"'।")


def nfc_claimant(text: str) -> str:
    """Who made the claim, from NFC's summary box ("" if not given)."""
    found = list(NFC_CLAIMANT.finditer("\n" + (text or "")))
    if not found:
        return ""
    return _flat(found[-1].group(1)).strip(" :ः।")


# Where the claim spread (claim_platform). Fixed order, joined with "|".
# Read from the claimant line (NFC) and the first 300 characters of the
# "दाबी" section (TechPana), where the outlet names the page or account.
_L = "\u0900-\u0963\u0971-\u097F"
PLATFORMS = (
    ("facebook",   r"फेसबुक|फेसबूक|facebook"),
    ("tiktok",     r"टिकटक|टिक\s*टक|tiktok"),
    ("x",          rf"(?<![{_L}])एक्स(?![{_L}])|ट्विटर|twitter|ट्वीट"),
    ("youtube",    r"युट्युब|यूट्यूब|youtube"),
    ("instagram",  r"इन्स्टाग्राम|इन्स्टाग्राम|instagram"),
    ("messaging",  r"ह्वाट्सएप|ह्वाट्सएप|भाइबर|मेसेन्जर|whatsapp|viber|messenger"),
    ("news_media", r"डटकम|डट\s*कम|\.com|दैनिक|पत्रिका|टेलिभिजन|(?<![{_L}])टिभी|अनलाइन|"
                   r"सञ्चार\s*माध्यम|कान्तिपुर|रातोपाटी|सेतोपाटी|गोरखापत्र|न्युज\s*पोर्टल"),
)
PLATFORM_VALUES = tuple(name for name, _ in PLATFORMS)


def find_platforms(text: str) -> str:
    """"facebook|news_media" etc. ("" if no platform is named)."""
    return "|".join(name for name, pat in PLATFORMS
                    if re.search(pat, text or "", re.IGNORECASE))


def extract_platform(source_name: str, claimant: str, body_text: str) -> str:
    """claim_platform column. "" means the article names no platform."""
    text = claimant or ""
    if source_name == "techpana":
        text += " " + tp_claim_section(body_text)[:300]
    return find_platforms(text)


def extract_claimant(source_name: str, body_text: str) -> str:
    """claimant column: NFC's दावीकर्ता line. TechPana has no such field."""
    return nfc_claimant(body_text) if source_name == "nepalfactcheck" else ""


def headline_question(headline: str) -> str:
    """NFC headline "के … हो?" -> the question without "?" ("" otherwise)."""
    h = _flat(headline)
    if re.match(r"^के\s", h) and h.endswith("?"):
        return h.rstrip(" ?")
    return ""


def tp_claim_section(text: str) -> str:
    """TechPana's "दाबी" section, flattened ("" if there is none)."""
    m = TP_CLAIM_HEADING.search("\n" + (text or ""))
    if not m:
        return ""
    rest = ("\n" + text)[m.end():]
    end = TP_SECTION_END.search(rest)
    return _flat(rest[:end.start()] if end else rest[:2000])


def tp_caption(text: str) -> str:
    """First quote of 8+ words in the "दाबी" section that sits next to a
    caption cue ("क्याप्सनमा ‘…’ लेखिएको छ") ("" if none)."""
    section = tp_claim_section(text)
    for m in TP_QUOTE.finditer(section):
        quote = _flat(m.group(1)).strip(" ।")
        context = section[max(0, m.start() - 120):m.end() + 60]
        if len(quote.split()) >= 8 and CAPTION_CUE.search(context) \
                and not leaks_verdict(quote):
            return quote[:500]
    return ""


def extract_claim(source_name: str, headline: str, evidence_text: str,
                  conclusion_text: str, body_text: str = "") -> tuple[str, str]:
    """Returns (claim_text, claim_source). body_text is the full raw body
    (the NFC box and the TechPana "दाबी" section are read from it; without
    it, evidence_text and conclusion_text are searched)."""
    full = body_text or (evidence_text + "\n" + conclusion_text)
    if source_name == "nepalfactcheck":
        box = nfc_claim_box(full)
        if box and _usable(box):
            return box, "claim_box"
        question = headline_question(headline)
        if question and _usable(question):
            return question, "headline_question"
    elif source_name == "techpana":
        caption = tp_caption(full)
        if caption and not leaks_verdict(caption):
            return caption, "claim_caption"
    return lead_claim(headline, evidence_text)


def lead_claim(headline: str, evidence_text: str) -> tuple[str, str]:
    """The fallback steps, both outlets: a quote in the lead, the lead
    sentence, the "दाबी" section's first sentence, the cleaned headline.
    (Also used by pipeline/claim_groups.py, so grouping does not depend on
    which step or person wrote claim_text.)"""
    lead = _lead_sentences(evidence_text[:1500])
    for i, sentence in enumerate(lead):
        if not VIRAL.search(sentence):
            continue
        if is_generic(sentence):
            # "a video is going viral." -> the claim is in the next sentence
            if i + 1 < len(lead) and not is_generic(lead[i + 1]):
                sentence = sentence + " " + lead[i + 1]
            else:
                continue
        # A quote is the claim only if it is a statement, not a name
        quotes = [q for q in QUOTE.findall(sentence)
                  if not leaks_verdict(q) and len(q.split()) >= 5]
        if quotes:
            return max(quotes, key=len).strip(), "lead_quote"
        if 20 <= len(sentence) <= 400 and not leaks_verdict(sentence):
            return sentence, "lead"

    heading = CLAIM_HEADING.search("\n" + evidence_text)
    if heading:
        for sentence in split_sentences(("\n" + evidence_text)[heading.end():])[:4]:
            if 20 <= len(sentence) <= 400 and not leaks_verdict(sentence) \
                    and not is_generic(sentence) \
                    and not re.match(r"^[\d१-९]+\)?$", sentence):
                return sentence, "claim_section"

    cleaned = clean_headline(headline)
    return (cleaned or (headline or "").strip()), "headline"


def claim_has_leak(claim_text: str) -> bool:
    """For tests: a verdict word left in a claim. (Cue words such as नक्कली
    are only removed from headlines: "नक्कली भुटानी शरणार्थी" is a topic.)"""
    return leaks_verdict(claim_text)
