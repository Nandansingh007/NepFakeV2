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

from config.settings import NFC_BOX_IN_EVIDENCE
from pipeline.text_rules import leaks_verdict, split_sentences
from scrapers.techpana import CONCLUSION_HEADING, extract_own_date, strip_sidebar

TP_CONCLUSION = CONCLUSION_HEADING   # scrapers/techpana.py (also "निष्कर्ष:" / "निश्कर्ष")
TP_FOOTER = re.compile(r"\n\s*प्रतिक्रिया\s*\n")
NFC_CONCLUSION = re.compile(r"\n\s*(?:तथ्य\s*जाँ+च\s*/\s*नि[ष्श]्कर्ष|नि[ष्श]्कर्ष)\s*:?\s*\n")
# NFC's summary box at the end of the article: "तथ्य जाँच" heading (optional),
# then "दावी : …", "दावीकर्ता : …", "तथ्य : <verdict>. <finding>". It is the
# fact-checker's own summary of the answer, like TechPana's निष्कर्ष box, so
# it goes to conclusion_text with it (config NFC_BOX_IN_EVIDENCE). The claim
# and the claimant are read from it into their own columns.
NFC_BOX_START = re.compile(r"(?:\n\s*(?:तथ्य\s*जाँ+च|तथ्यजाँ+च)\s*)?\n\s*दा[वब]ी\s*[:ः]")
NFC_FOOTER = "प्रतिक्रिया दिनुहोस्"
NFC_BS_DATE = re.compile(r"^(?:बैशाख|वैशाख|जेठ|जेष्ठ|असार|आषाढ|साउन|श्रावण|भदौ|भाद्र|असोज|अशोज|आश्विन|"
                         r"कात्तिक|कार्तिक|मंसिर|मङ्सिर|पुस|पौष|माघ|फागुन|फाल्गुन|चैत|चैत्र)\s+[०-९\d]+")


# Links are in external_evidence_urls. In evidence_text they were a shortcut:
# NFC's own upload links (".../wp-content/uploads/2026/11/x.mp4") carry the
# date and the media type, and were in 26% of MISLEADING but 13% of FALSE
# benchmark rows (28 Nov 2026).
URL = re.compile(r"https?://\S+|www\.\S+")
# The outlet naming itself ("टेकपाना फ्याक्टचेक डेस्कले …") tells a model the
# source, which is a column of its own and correlates with the label.
OUTLET = re.compile(r"टेकपाना|नेपाल\s*फ्याक्ट\s*चेक|नेपालफ्याक्टचेक|tech\s*pana|nepal\s*fact\s*check",
                    re.I)
OUTLET_TOKEN = "[OUTLET]"
# A conclusion heading left at the very end (heading written inline)
TRAILING_HEADING = re.compile(r"\s*नि[ष्श]्कर्ष\s*[:ः]\s*$")


def mask_shortcuts(text: str) -> str:
    """Remove links and replace the outlet's own name (evidence_text only)."""
    text = URL.sub(" ", text)
    text = OUTLET.sub(OUTLET_TOKEN, text)
    text = TRAILING_HEADING.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


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
    if not NFC_BOX_IN_EVIDENCE:
        boxes = list(NFC_BOX_START.finditer("\n" + text))
        if boxes:
            b = boxes[-1]
            box = ("\n" + text)[b.start():].strip()
            text = ("\n" + text)[:b.start()].strip()
            conclusion = (box + "\n" + conclusion).strip()
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
    return mask_shortcuts(_drop_leaking_sentences(text)), conclusion
