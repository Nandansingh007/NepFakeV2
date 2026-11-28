# pipeline/claim_extractor.py
# =============================================================================
# Brief item L1: the claim, not the fact-checker's headline.
#
# The headline gives the answer away ("... दाबी भ्रामक", "नझुक्किनुस्").
# Order (first that works wins; claim_source says which):
#   1. "claim_box"   NFC's conclusion box line "दाबी : ‘…’" (newer articles)
#   2. "lead_quote"  the quoted claim inside the lead sentence:
#                    सामाजिक सञ्जालमा “<claim>” भन्दै भिडिओ भाइरल छ
#   3. "lead"        the lead sentence that reports the viral claim
#   4. "claim_section" the first sentence under the "दाबी" / "के हो दाबी ?" heading
#   5. "headline"    the headline with prefixes, verdict and cue words removed
# Steps 1-4 are rejected if they contain a verdict word.
#
# This is rule-based. The brief asks for a 50-claim hand check (not code);
# report its result per claim_source.
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
NFC_CLAIM_LINE = re.compile(r"\n\s*दाबी\s*:\s*\n?\s*[‘“\"']?(.{15,400}?)[’”\"']?\s*(?:भन्दै|\n)")


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


def extract_claim(source_name: str, headline: str, evidence_text: str,
                  conclusion_text: str) -> tuple[str, str]:
    """Returns (claim_text, claim_source)."""
    if source_name == "nepalfactcheck" and conclusion_text:
        m = NFC_CLAIM_LINE.search("\n" + conclusion_text)
        if m and not leaks_verdict(m.group(1)):
            return m.group(1).strip(" ‘’“”\"'"), "claim_box"

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
