# pipeline/text_rules.py
# =============================================================================
# Word lists and small text helpers shared by the claim extractor, the
# evidence cleaner and the leakage tests. One list, so the tests check
# exactly what the cleaners remove.
# =============================================================================

import re

# Verdict words: any of these in a model input gives the label away.
VERDICT_WORDS = [
    "मिथ्या", "भ्रामक", "अपुष्ट", "झुटो", "झूटो", "असत्य", "गलत", "भ्रम",
]
# "True" words only count as a verdict inside a finding sentence (they are
# ordinary words elsewhere: "यो कुरा सत्य हो" in a narrative).
TRUE_WORDS = ["सही", "सत्य", "साँचो"]

# Cue words in fact-checker headlines that hint at the verdict
CUE_WORDS = [
    "नझुक्किनुस्", "नझुक्किनुहोस्", "नक्कली", "फेक", "झुक्किनुभयो",
    "भ्रममा", "हल्ला",
]

# Headline prefixes ("फ्याक्टचेक:", "टेकपाना फ्याक्टचेकः", "Fact Check:")
HEADLINE_PREFIX = re.compile(
    r"^\s*(?:टेकपाना\s*)?(?:फ्याक्ट\s*चेक|फ्याक्टचेक|तथ्य\s*जाँच|fact[\s\-]*check)\s*[:ः\-–—!]*\s*",
    re.IGNORECASE)

# Sentences that report the fact-checker's finding
FINDING_CUE = re.compile(
    r"फ्याक्ट\s*चेक|फ्याक्टचेक|तथ्य\s*जाँच|तथ्यजाँच|पुष्टि|नेपालफ्याक्टचेक|अनुसन्धानबाट|ठहर")
# NFC's verdict phrase, also inside older articles' "तथ्य : सही सूचना" box
VERDICT_PHRASE = re.compile(r"(?:सही|सत्य|साँचो|मिथ्या|भ्रामक|अपुष्ट)\s*सूचना")

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN = re.compile(r"[A-Za-z]")


# Devanagari letters and vowel signs, NOT the danda (।, ॥) or the digits:
# "भ्रामक।" is the word भ्रामक followed by a full stop. (Before 28 Nov 2026
# the danda counted as a letter, so "तथ्य : भ्रामक।" was not caught.)
_LETTER = "\u0900-\u0963\u0971-\u097F"

# Tag words that are never anything but a verdict, so any word that starts
# with them counts too: भ्रामकका, भ्रामकता, मिथ्यापूर्ण, अपुष्टता.
# (भ्रम and गलत stay whole-word only: भ्रमण is travel, गलती is a mistake.)
TAG_STEMS = ["मिथ्या", "भ्रामक", "अपुष्ट"]


def has_word(text: str, words) -> bool:
    """Whole-word match for Devanagari (भ्रम must not match भ्रमण)."""
    return any(
        re.search(rf"(?<![{_LETTER}]){re.escape(w)}(?![{_LETTER}])", text or "")
        for w in words)


def has_tag_stem(text: str) -> bool:
    """A word starting with a verdict tag (मिथ्या…, भ्रामक…, अपुष्ट…)."""
    return any(re.search(rf"(?<![{_LETTER}]){w}", text or "") for w in TAG_STEMS)


def leaks_verdict(sentence: str) -> bool:
    """True if a sentence gives the verdict away."""
    if has_word(sentence, VERDICT_WORDS) or has_tag_stem(sentence) \
            or VERDICT_PHRASE.search(sentence or ""):
        return True
    if re.search(r"\b(?:misleading|false|fake|unverified)\b", sentence or "", re.I):
        return True
    return bool(FINDING_CUE.search(sentence or "")) and has_word(sentence, TRUE_WORDS)


def split_sentences(text: str) -> list[str]:
    """Split on the danda (।), ? and line breaks; keep non-empty pieces."""
    parts = re.split(r"(?<=[।?!|])\s*|\n+", (text or "").replace("\xa0", " "))
    return [p.strip() for p in parts if p and p.strip()]


def devanagari_share(text: str) -> float:
    """Share of letters that are Devanagari (0..1); 0 if no letters."""
    dev = len(DEVANAGARI.findall(text or ""))
    lat = len(LATIN.findall(text or ""))
    return dev / (dev + lat) if dev + lat else 0.0


def text_leaks(text: str) -> bool:
    """True if any sentence of a text gives the verdict away. (Checked per
    sentence: a finding cue in one sentence and an ordinary सही in another
    is not a verdict.)"""
    return any(leaks_verdict(s) for s in split_sentences(text))
