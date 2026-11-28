# pipeline/evidence_cleaner.py
# =============================================================================
# Brief item L2: evidence without the answer.
#
# body_text (the whole article) contains the verdict several times: NFC's tag
# line, the headline, the summary's finding sentence, the conclusion box. A
# word counter on body_text scored 93.5% on FALSE vs MISLEADING. This module
# builds:
#   evidence_text    the article body with the header, the conclusion, the
#                    footer/sidebar and every verdict-bearing sentence removed
#   conclusion_text  the fact-checker's conclusion, kept separately
#                    (for annotation and audits; NEVER a model input)
#
# The raw layer keeps the full body_text, unchanged.
# =============================================================================

import re

from pipeline.text_rules import leaks_verdict, split_sentences
from scrapers.techpana import extract_own_date, strip_sidebar

TP_CONCLUSION = re.compile(r"\n\s*निष्कर्ष\s*\n")
TP_FOOTER = re.compile(r"\n\s*प्रतिक्रिया\s*\n")
NFC_CONCLUSION = re.compile(r"\n\s*(?:तथ्य\s*जाँच\s*/\s*निष्कर्ष|निष्कर्ष)\s*:?\s*\n")
NFC_FOOTER = "प्रतिक्रिया दिनुहोस्"
NFC_BS_DATE = re.compile(r"^(?:बैशाख|वैशाख|जेठ|जेष्ठ|असार|आषाढ|साउन|श्रावण|भदौ|भाद्र|असोज|अशोज|आश्विन|"
                         r"कात्तिक|कार्तिक|मंसिर|मङ्सिर|पुस|पौष|माघ|फागुन|फाल्गुन|चैत|चैत्र)\s+[०-९\d]+")


def _drop_leaking_sentences(text: str) -> str:
    kept = [s for s in split_sentences(text) if not leaks_verdict(s)]
    return "\n".join(kept).strip()


def _techpana(title: str, body: str) -> tuple[str, str]:
    start = 0
    own_date = extract_own_date(body)
    if own_date:
        line_end = body.find("\n", body.index(own_date))
        start = line_end + 1 if line_end != -1 else 0
    elif body.startswith(title):
        start = len(title)
    text = body[start:]

    conclusion = ""
    heads = list(TP_CONCLUSION.finditer(text))
    if heads:
        after = text[heads[-1].end():]
        foot = TP_FOOTER.search("\n" + after)
        conclusion = strip_sidebar(after[:foot.start()] if foot else after).strip()
        text = text[:heads[-1].start()]
    else:
        foot = TP_FOOTER.search(text)
        if foot:
            text = text[:foot.start()]
    return strip_sidebar(text), conclusion


def _nfc(title: str, body: str) -> tuple[str, str]:
    lines = body.split("\n")
    start = None
    # Content starts after the second copy of the title (header: menu, tag
    # line, title, breadcrumbs, author, date, title again)
    title_hits = [i for i, l in enumerate(lines[:20]) if l.strip() == title.strip()]
    if len(title_hits) >= 2:
        start = title_hits[1] + 1
    else:
        for i, l in enumerate(lines[:20]):
            if NFC_BS_DATE.match(l.strip()):
                start = i + 1
                if start < len(lines) and lines[start].strip() == title.strip():
                    start += 1
                break
    text = "\n".join(lines[start if start is not None else 0:])

    cut = text.find(NFC_FOOTER)
    if cut != -1:
        text = text[:cut]

    conclusion = ""
    heads = list(NFC_CONCLUSION.finditer("\n" + text))
    if heads:
        h = heads[-1]
        conclusion = ("\n" + text)[h.end():].strip()
        text = ("\n" + text)[:h.start()].strip()
    return text, conclusion


def clean_evidence(source_name: str, title: str, body_text: str) -> tuple[str, str]:
    """
    Returns (evidence_text, conclusion_text).

    evidence_text has no verdict words (pipeline/text_rules.VERDICT_WORDS)
    and no finding sentence; it may be short or empty for very short
    articles (the validator warns, it does not drop the row).
    """
    body = (body_text or "").strip()
    if source_name == "techpana":
        text, conclusion = _techpana(title or "", body)
    elif source_name == "nepalfactcheck":
        text, conclusion = _nfc(title or "", body)
    else:
        text, conclusion = body, ""
    return _drop_leaking_sentences(text), conclusion
