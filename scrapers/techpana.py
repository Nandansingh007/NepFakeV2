# scrapers/techpana.py
# =============================================================================
# TechPana fact-check scraper.
# Scrapes: techpana.com/factcheck/?tab=nepali&page={n}
#
# HTML structure (verified 31 Aug 2026):
#   Article cards: <h3><a href="/2026/XXXXXX/slug">title</a></h3>
#   Date:          Plain text — "भदौ ९, २०८३ १६:८" (BS format)
#   Verdict:       conclusion box, then lead summary, then og:image
#                  filename e.g. "False_xxx.jpg" (see resolve_verdict)
#   Pagination:    ?tab=nepali&page={n}
#
# Stage 1 principles:
#   - date_published stored as raw BS string — NO conversion
#   - published_date_iso computed internally for cutoff check ONLY
#   - published_date_iso NOT stored in raw JSON
#
# Fixes (05 Sep 2026):
#   - Added झुटो, साँचो, गलत to VERDICT_KEYWORDS
#   - Fixed img src search to check ALL img tags not just first
# Fix (10 Sep 2026):
#   - Strip leading "Shares\n" widget artifact from body_text
# Fixes (12 Oct 2026), all checked against the 275 raw articles:
#   - Date: take the article's own date line (first BS date in body_text).
#     The old loop searched the whole page in calendar-month order and often
#     returned a sidebar date: 145 of 275 dates were wrong (148 articles got
#     "भदौ २६, २०८३").
#   - Verdict: removed the search over ALL <img> tags (it picked sidebar
#     badges). Body fallback now reads only the LAST "निष्कर्ष" section
#     (found before stripping the sidebar), ignores negations such as
#     "सही होइन", matches whole words, and returns a verdict only if exactly
#     one is named.
#   - is_factcheck_article() was defined but never called; it is now called,
#     with a stricter test (dropped 4 non-fact-checks: ChatGPT tips, Redmi,
#     iPhone, an EV-fire news story).
# Fix (Nov 2026, Phase 1):
#   - Verdict order was badge first, conclusion second; the normalizer used
#     the reverse, so 54 raw verdicts disagreed with the dataset. Both now
#     call resolve_verdict(): conclusion, then lead summary, then badge, and
#     it also says where the verdict came from (label_source).
#   - "गलत" maps to भ्रामक (misleading), not मिथ्या.
# =============================================================================

import copy
import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from nepali_datetime import date as NepaliDate

from scrapers.base import BaseScraper
from schema.schema import RawArticle


# =============================================================================
# BS MONTH NAMES + DATE HELPERS
# =============================================================================

BS_MONTHS = {
    "बैशाख": 1, "जेठ": 2,  "असार": 3,  "साउन": 4,
    "भदौ":   5, "असोज": 6, "कात्तिक": 7, "मंसिर": 8,
    "पुस":   9, "माघ": 10, "फागुन": 11, "चैत": 12,
}

NEPALI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def nepali_to_ascii(text: str) -> str:
    return text.translate(NEPALI_DIGITS)


def parse_bs_date(date_str: str) -> Optional[str]:
    """
    Convert BS date string to ISO format.
    Used ONLY for published_date_iso (cutoff comparison).
    NOT used for storage — raw string stored as-is.
    """
    try:
        date_str = date_str.strip()
        date_str = date_str.replace("अशोज", "असोज")  # normalize NFC spelling
        parts = date_str.split()
        if len(parts) < 3:
            return None

        month_name = parts[0].strip()
        day_str    = nepali_to_ascii(parts[1].replace(",", "").strip())
        year_str   = nepali_to_ascii(parts[2].strip())

        bs_month = BS_MONTHS.get(month_name)
        if not bs_month:
            return None

        nepali_date_obj = NepaliDate(int(year_str), bs_month, int(day_str))
        ad_date = nepali_date_obj.to_datetime_date()
        return ad_date.strftime("%Y-%m-%d")

    except Exception:
        return None


def parse_bs_date_from_text(text: str) -> Optional[str]:
    """
    Extract and convert the first BS date found in a text block.
    Used to get date_iso from listing page card text.
    Returns ISO "YYYY-MM-DD" or None.
    """
    text = text.replace("अशोज", "असोज")  # normalize NFC spelling
    for month in BS_MONTHS.keys():
        pattern = rf"{month}\s+[०-९\d]+,?\s+[०-९\d]{{4}}"
        match = re.search(pattern, text)
        if match:
            return parse_bs_date(match.group(0))
    return None


def date_iso_from_url(url: str) -> Optional[str]:
    """
    Extract approximate date from TechPana URL pattern /YYYY/NNNNNN/.
    The 6-digit segment encodes YYYYMM — use as YYYY-MM-01 fallback.
    Returns "YYYY-MM-01" or None.
    """
    match = re.search(r"/(\d{4})/(\d{6})/", url)
    if match:
        year = match.group(1)
        month_segment = match.group(2)[:2]   # first 2 digits = month
        try:
            month = int(month_segment)
            if 1 <= month <= 12:
                return f"{year}-{month:02d}-01"
        except ValueError:
            pass
    return None


def extract_own_date(body_text: str) -> Optional[str]:
    """
    The article's own date line, e.g. "साउन ६, २०८३ १६:१०" under the author:
    the FIRST BS date (by position) in the first 400 chars of body_text.
    Found for 274 of 275 articles (Oct 2026).
    """
    if not body_text:
        return None
    months = "|".join(BS_MONTHS.keys())
    match = re.search(rf"(?:{months})\s+[०-९\d]+,?\s+[०-९\d]{{4}}", body_text[:400])
    return match.group(0) if match else None


# =============================================================================
# VERDICT EXTRACTION
# =============================================================================

# FIXED: added informal Nepali verdict words
VERDICT_KEYWORDS = {
    # Standard Nepali
    "मिथ्या": "मिथ्या",
    "भ्रामक": "भ्रामक",
    "अपुष्ट": "अपुष्ट",
    "सही":    "सही",
    # Informal Nepali
    "झुटो":   "मिथ्या",   # informal "false"
    "साँचो":  "सही",      # informal "true"
    # "गलत" ("wrong") is NOT a plain keyword: its meaning depends on the
    # next word (GALAT_FALSE / GALAT_MISLEADING below, 28 Nov 2026).
    "सत्य":   "सही",      # formal "true"
    "असत्य":  "मिथ्या",   # formal "untrue"
    "भ्रम":   "भ्रामक",   # "confusion/misleading"
}

IMAGE_VERDICT_MAP = {
    "false":      "मिथ्या",
    "misleading": "भ्रामक",
    "unverified": "अपुष्ट",
    "verified":   "सही",
}

# Sidebar markers — strip content after these to avoid false positives
SIDEBAR_MARKERS = [
    "सम्बन्धित समाचार",   # related news
    "ट्रेन्डिङ समाचार",    # trending news
    "पछिल्लो अध्यावधिक",  # last updated
    "टिप्पणीहरू",          # comments
    "पछिल्ला अपडेट",      # latest updates
]

# Factcheck indicators — article must have one to be included
FACTCHECK_INDICATORS = [
    "फ्याक्टचेक",
    "टेकपाना फ्याक्टचेक",
    "fact check",
    "factcheck",
    "fact-check",
    "fact-check:",
    "निष्कर्ष",
    "misleading",
]


def strip_sidebar(text: str) -> str:
    """Remove sidebar/related content to prevent false positives."""
    for marker in SIDEBAR_MARKERS:
        idx = text.find(marker)
        if idx != -1:
            text = text[:idx]
    return text


def strip_shares_prefix(text: str) -> str:
    """
    Remove leading "Shares" widget artifact from TechPana body text.
    TechPana injects a social share count widget at the top of article
    content — it renders as "Shares\n" before the actual article text.
    Affects ~72% of TechPana articles.
    """
    if text.startswith("Shares"):
        newline_idx = text.find("\n")
        if newline_idx != -1:
            return text[newline_idx + 1:].strip()
    return text


# Text the sidebar starts with; every complete article page has it after the
# article text (265 of 275 pages in the 28 Nov 2026 full re-scrape).
PAGE_END_MARKER = "पछिल्ला अपडेट"
PAGE_RETRIES = 2


def content_container(soup):
    """The element that holds the article text (first match wins)."""
    return (
        soup.find("div", class_="article-content") or
        soup.find("div", class_="content") or
        soup.find("article") or
        soup.find("main")
    )


def article_body(soup) -> str:
    """Article text of a parsed page, as stored in body_text. Does not change
    the soup (scripts are skipped, not removed), so it can be called twice."""
    div = content_container(soup)
    if not div:
        return ""
    div = copy.copy(div)               # same text as before, soup untouched
    for tag in div.find_all(["script", "style", "nav"]):
        tag.decompose()
    return strip_shares_prefix(div.get_text(separator="\n", strip=True))


def page_reaches_end(body_text: str) -> bool:
    """True if the text runs to the sidebar, i.e. the page was not cut short."""
    return PAGE_END_MARKER in body_text


def is_factcheck_article(title: str, body_text: str, url: str = "") -> bool:
    """
    Check if article is a fact-check article.
    Filters out regular news articles that slip through listing page.

    Keep if ANY of:
      - "फ्याक्टचेक" / "तथ्य जाँच" / "fact check" in title or URL
      - a summary box ("दाबी" heading + "तथ्य" or "निष्कर्ष" heading)
      - a verdict word early in the article (reports without a box)
    """
    if re.search(r"फ्याक्ट\s*चेक|तथ्य\s*जाँच|fact[\s\-]*check", f"{title} {url}", re.I):
        return True
    if (re.search(r"\n\s*दा[बव]ी\s*\n", body_text)
            and re.search(r"\n\s*(तथ्य|निष्कर्ष)\s*\n", body_text)):
        return True
    return bool(re.search(r"भ्रामक|मिथ्या|झुटो|भ्रम फैला", strip_sidebar(body_text)[:1500]))


def extract_verdict_from_image(img_url: str) -> Optional[str]:
    if not img_url:
        return None
    img_lower = img_url.lower()
    for keyword, verdict in IMAGE_VERDICT_MAP.items():
        if keyword in img_lower:
            return verdict
    return None


# "सही होइन" / "सत्य छैन" means NOT true: these phrases are dropped before
# looking for verdict words
NEGATED_TRUE = re.compile(
    r"(?:सही|सत्य|साँचो)\s*(?:हो\s*)?(?:होइन|हैन|छैन|होइनन्|नभएको|नरहेको|हुँदैन|ठहरिँदैन)")

# The conclusion box heading: "निष्कर्ष" on its own line, also spelled
# "निश्कर्ष" or followed by a colon ("निष्कर्ष:", 28 Nov 2026).
CONCLUSION_HEADING = re.compile(r"\n\s*नि[ष्श]्कर्ष\s*[:ः]?\s*\n")

# "X सत्य भए पनि / सही भए तापनि …" = "although X is true, …": a concession
# about a side fact, not the verdict (28 Nov 2026: 6 TechPana conclusions,
# e.g. 158844 "घटना सत्य भए तापनि … भिडिओ … भ्रामक हो", lost their verdict).
CONCESSIVE_TRUE = re.compile(
    r"(?<![\u0900-\u097F])(?:सही|सत्य|साँचो)\s*(?:हो\s*)?"
    r"(?:भए\s*(?:ता)?\s*पनि|भएता\s*पनि|भएतापनि|भएपनि)")

# Summary sentences that report the desk's finding, e.g.
# "तर, टेकपाना फ्याक्टचेक डेस्कको अनुसन्धानबाट उक्त दाबी मिथ्या रहेको पुष्टि भएको छ ।"
FINDING_CUE = re.compile(r"फ्याक्ट\s*चेक|तथ्य\s*जाँच|अनुसन्धान|पुष्टि")


# "गलत" by context (TechPana conclusions, 28 Nov 2026 full re-scrape):
#   "दाबी गलत हो / रहेको / भएको / ठहरिएको" the claim is wrong      -> मिथ्या
#   "गलत सन्दर्भ / अर्थ / व्याख्या / तरिका" wrong context or meaning  -> भ्रामक
#   "गलत सूचना / प्रचार", "गलत र …"     misinformation in general -> not a verdict
GALAT_FALSE = re.compile(
    r"(?<![\u0900-\u097F])गलत\s*(?:हो|हुन्|रहेको|भएको|ठहरिएको|ठहर्‍याइएको|पाइएको|देखिएको|साबित)"
    r"(?![\u0900-\u097F])")
GALAT_MISLEADING = re.compile(
    r"(?<![\u0900-\u097F])गलत\s*(?:सन्दर्भ|अर्थ|व्याख्या|तरिका|रूप|ढङ्ग|ढंग|दिशा)")


def named_verdicts(text: str) -> set:
    """
    The set of verdicts a piece of text names, e.g. {"मिथ्या"} or
    {"मिथ्या", "भ्रामक"}. Negated "true" phrases are ignored, and keywords
    match whole words only ("भ्रम" must not match "भ्रमण").
    """
    if not text:
        return set()
    text = NEGATED_TRUE.sub(" ", text)
    text = CONCESSIVE_TRUE.sub(" ", text)
    found = {
        verdict for keyword, verdict in VERDICT_KEYWORDS.items()
        if re.search(rf"(?<![\u0900-\u097F]){re.escape(keyword)}(?![\u0900-\u097F])", text)
    }
    if GALAT_FALSE.search(text):
        found.add("मिथ्या")
    if GALAT_MISLEADING.search(text):
        found.add("भ्रामक")
    return found


def claim_sentence_verdicts(body_text: str) -> set:
    """Verdicts named in the conclusion's sentences about the claim (those
    containing दाबी/दावी). Empty set if there is no such sentence."""
    headings = list(CONCLUSION_HEADING.finditer(body_text or ""))
    if not headings:
        return set()
    conclusion = strip_sidebar(body_text[headings[-1].end():])
    sentences = [s for s in re.split(r"[।\n]", conclusion) if re.search(r"दा[बव]ी", s)]
    return set().union(*(named_verdicts(s) for s in sentences)) if sentences else set()


def conclusion_verdicts(body_text: str) -> Optional[set]:
    """
    Verdicts named in the LAST "निष्कर्ष" section (the conclusion box, not
    the narrative). None if the article has no "निष्कर्ष" heading.

    The heading is found BEFORE stripping the sidebar: TechPana puts a
    "सम्बन्धित समाचार" box inside the article, and stripping first threw
    the conclusion away.
    """
    if not body_text:
        return None
    headings = list(CONCLUSION_HEADING.finditer(body_text))
    if not headings:
        return None
    return named_verdicts(strip_sidebar(body_text[headings[-1].end():]))


def conclusion_text_for_sheet(body_text: str) -> str:
    """Text after the last "निष्कर्ष" heading (sidebar cut), or "" if none.
    Shown to the person in the label hand-check sheet."""
    headings = list(CONCLUSION_HEADING.finditer(body_text or ""))
    if not headings:
        return ""
    return " ".join(strip_sidebar(body_text[headings[-1].end():]).split())


def extract_verdict_from_body(body_text: str) -> Optional[str]:
    """
    Verdict from the conclusion box, only if it names exactly one verdict.
    Otherwise None (no heading, no verdict word, or several verdicts).
    """
    found = conclusion_verdicts(body_text)
    return next(iter(found)) if found and len(found) == 1 else None


def extract_verdict_from_summary(body_text: str) -> Optional[str]:
    """
    Verdict from the lead summary: the paragraphs between the article's own
    date line and the first "दाबी" heading. Only sentences that report the
    desk's finding count (FINDING_CUE). Returns a verdict only if exactly
    one is named; None if there is no "दाबी" heading.
    """
    if not body_text:
        return None
    claim_heading = re.search(r"\n\s*दा[बव]ी\s*\n", body_text)
    if not claim_heading:
        return None
    lead = body_text[:claim_heading.start()]
    own_date = extract_own_date(lead)
    if own_date:
        lead = lead[lead.index(own_date) + len(own_date):]
    sentences = [s for s in re.split(r"[।\n]", lead) if FINDING_CUE.search(s)]
    found = set().union(*(named_verdicts(s) for s in sentences)) if sentences else set()
    return next(iter(found)) if len(found) == 1 else None


def resolve_verdict(body_text: str, fallback: str = "") -> tuple[str, str]:
    """
    THE verdict rule for TechPana, used by both the scraper and the
    normalizer, so the two can never disagree again.

    Order (first match wins):
      1. the conclusion box names exactly one verdict
             -> (that verdict, "conclusion")
      2. the conclusion names several verdicts: look only at its sentences
         about the claim (दाबी)
           a. they name exactly one of them -> (that one, "conclusion_claim")
              (e.g. "… दाबी मिथ्या हो", with भ्रामक only in "भ्रामक पोस्ट")
           b. otherwise, if the verdicts are मिथ्या and भ्रामक
                                            -> ("भ्रामक", "conclusion_mixed")
              (any other combination goes on to step 3)
              Rule decided 28 Nov 2026: a verdict naming both is MISLEADING.
              There is no MIXED label any more.
      3. the lead summary names exactly one verdict
             -> (that verdict, "summary")
      4. otherwise
             -> (fallback, "stored")
    The label_source values are documented in config/settings.py
    LABEL_SOURCES.

    Args:
        body_text: article body text
        fallback:  the value to fall back on (the og:image badge in the
                   scraper, the stored raw_verdict_text in the normalizer)

    Returns:
        (verdict, label_source). verdict is "" if nothing was found.
    """
    fallback = (fallback or "").strip()

    found = conclusion_verdicts(body_text)
    if found and len(found) == 1:
        return next(iter(found)), "conclusion"
    if found and len(found) > 1:
        claim = claim_sentence_verdicts(body_text) & found
        if len(claim) == 1:
            return next(iter(claim)), "conclusion_claim"
        if found == {"मिथ्या", "भ्रामक"}:
            return "भ्रामक", "conclusion_mixed"

    summary = extract_verdict_from_summary(body_text)
    if summary:
        return summary, "summary"

    return fallback, "stored"


# =============================================================================
# TECHPANA SCRAPER
# =============================================================================

class TechpanaScraper(BaseScraper):
    """
    Scraper for TechPana Nepali fact-checks.
    techpana.com/factcheck/?tab=nepali&page={n}
    Incremental: last_published_date from last_run.json
    """

    def __init__(self):
        super().__init__("techpana")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[tuple[str, str]]:
        """
        Extract article URLs and listing-page dates from TechPana listing page.

        Returns:
            List of (url, date_iso) tuples.
            date_iso extracted from card text (BS date → ISO).
            Falls back to URL-derived approximate date if card date missing.
            Returns "" if neither available — article will be fetched anyway.
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        link_tuples = []
        seen = set()

        def process_card(container):
            """Extract (url, date_iso) from an article card container."""
            a = container.find("a", href=True)
            if not a:
                return

            href = a["href"]
            url = href if href.startswith("http") else urljoin("https://techpana.com", href)

            # Filter to Nepali fact-check URLs only
            if not re.search(r"/\d{4}/\d+/", url):
                return
            if "factcheck_eng" in url or "/english/" in url:
                return
            if url in seen:
                return

            # Extract date from card text — avoids fetching article
            card_text = container.get_text(" ", strip=True)
            date_iso = parse_bs_date_from_text(card_text) or date_iso_from_url(url) or ""

            seen.add(url)
            link_tuples.append((url, date_iso))

        # Strategy 1: single_row-title divs (current structure)
        for div in soup.find_all("div", class_="single_row-title"):
            # Walk up to find the card container that includes the date
            card = div.find_parent("div", class_=re.compile(r"single_row|card|item", re.I)) or div
            process_card(card)

        # Strategy 2: h3 tags (fallback for old structure)
        if not link_tuples:
            for h3 in soup.find_all("h3"):
                card = h3.find_parent("div", class_=re.compile(r"row|card|item|post", re.I)) or h3
                process_card(card)

        self.logger.debug(
            f"Found {len(link_tuples)} Nepali article links on {page_url}"
        )
        return link_tuples

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single TechPana fact-check article.

        Sets two date fields:
          date_published:     raw BS string stored in JSON as-is
          published_date_iso: ISO date for cutoff tracking, NOT stored
        """
        html = self.fetch_page(url)
        if not html:
            self.logger.warning(f"Failed to fetch: {url}")
            return None

        # A page whose text stops before the "पछिल्ला अपडेट" sidebar was cut
        # short (28 Nov 2026 full re-scrape: 10 of 275 pages ended right after
        # a "हेर्नुहोस् … स्क्रिनशट" link block, at a different point in each
        # scrape of the same article, so the HTML we got was incomplete, not
        # the article). Fetch it again, keep the longest text, and record
        # whether the end was reached (page_complete).
        soup = BeautifulSoup(html, "lxml")
        page_complete = page_reaches_end(article_body(soup))
        for attempt in range(PAGE_RETRIES):
            if page_complete:
                break
            self.logger.warning(f"Page text cut short, fetching again ({attempt + 1}/"
                                f"{PAGE_RETRIES}): {url}")
            again = self.fetch_page(url)
            if not again:
                continue
            again_soup = BeautifulSoup(again, "lxml")
            if len(article_body(again_soup)) > len(article_body(soup)):
                soup = again_soup
            page_complete = page_reaches_end(article_body(soup))
        if not page_complete:
            self.logger.warning(f"Page text still cut short after {PAGE_RETRIES} retries: {url}")

        try:
            # --- Title ---
            title = ""
            h1 = soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)
            if not title:
                self.logger.warning(f"No title: {url}")
                return None

            # --- Body text ---
            content_div = content_container(soup)
            # Strips the leading "Shares" widget artifact (~72% of articles)
            body_text = article_body(soup)

            if not body_text:
                self.logger.warning(f"No body text: {url}")
                return None

            if not is_factcheck_article(title, body_text, url):
                self.logger.info(f"Skipping — not a fact-check: {url}")
                return None

            # --- Author ---
            author = ""  # JS-rendered, skipped for now

            # --- Date ---
            date_published = ""
            published_date_iso = ""

            # The article's own date line (the old whole-page search in
            # calendar order often returned a sidebar date)
            own_date = extract_own_date(body_text)
            if own_date:
                date_published = own_date
                published_date_iso = parse_bs_date(own_date) or ""

            if not date_published:
                year_match = re.search(r"/(\d{4})/", url)
                if year_match:
                    date_published = year_match.group(1)
                    published_date_iso = f"{year_match.group(1)}-01-01"
                    self.logger.warning(f"Date fallback to year only: {url}")

            # --- Verdict ---
            # One rule for scraper and normalizer: conclusion, then lead
            # summary, then the og:image badge (see resolve_verdict).
            # Until Nov 2026 the badge was read FIRST here, while the
            # normalizer read the conclusion first, so raw files stored
            # verdicts the dataset then overrode (54 TechPana rows).
            badge, badge_url = "", ""
            og_image = soup.find("meta", property="og:image")
            if og_image:
                badge_url = og_image.get("content", "") or ""
                badge = extract_verdict_from_image(badge_url) or ""

            # (Removed Oct 2026: search over ALL <img> tags, which returned
            #  badges of sidebar articles.)

            raw_verdict, label_source = resolve_verdict(body_text, badge)

            if not raw_verdict:
                self.logger.warning(f"No verdict found: {url}")
            elif badge and raw_verdict != badge:
                self.logger.info(
                    f"Badge says {badge}, {label_source} says {raw_verdict}: {url}"
                )

            # --- External links ---
            external_links = []
            if content_div:
                for a in content_div.find_all("a", href=True):
                    href = a["href"]
                    if href.startswith("http") and "techpana.com" not in href:
                        external_links.append(href)

            article = RawArticle(
                source_name="techpana",
                source_url=url,
                title=title,
                body_text=body_text,
                raw_verdict_text=raw_verdict,
                date_published=date_published,
                published_date_iso=published_date_iso,
                date_scraped=date.today().isoformat(),
                author=author,
                category="factcheck",
                external_links=external_links[:20],
                badge_url=badge_url,
                page_complete=page_complete,
            )

            self.logger.debug(
                f"Scraped: {title[:60]} | "
                f"verdict: {raw_verdict} | "
                f"date_raw: {date_published} | "
                f"date_iso: {published_date_iso}"
            )
            return article

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None