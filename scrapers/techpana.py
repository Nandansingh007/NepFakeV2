# scrapers/techpana.py
# =============================================================================
# TechPana fact-check scraper.
# Scrapes: techpana.com/factcheck/?tab=nepali&page={n}
#
# HTML structure (verified 31 Aug 2026):
#   Article cards: <h3><a href="/2026/XXXXXX/slug">title</a></h3>
#   Date:          Plain text — "भदौ ९, २०८३ १६:८" (BS format)
#   Verdict:       og:image filename e.g. "False_xxx.jpg"
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
# =============================================================================

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
    "गलत":    "मिथ्या",   # "wrong"
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


def is_factcheck_article(title: str, body_text: str) -> bool:
    """
    Check if article is a fact-check article.
    Filters out regular news articles that slip through listing page.
    """
    combined = (title + " " + body_text[:500]).lower()
    return any(ind.lower() in combined for ind in FACTCHECK_INDICATORS)


def extract_verdict_from_image(img_url: str) -> Optional[str]:
    if not img_url:
        return None
    img_lower = img_url.lower()
    for keyword, verdict in IMAGE_VERDICT_MAP.items():
        if keyword in img_lower:
            return verdict
    return None


def extract_verdict_from_body(body_text: str) -> Optional[str]:
    """
    Extract verdict from body text.
    Strips sidebar first, then searches conclusion section,
    then full cleaned body.
    """
    if not body_text:
        return None

    # Strip sidebar content first
    clean_text = strip_sidebar(body_text)

    # Search conclusion section first
    conclusion_idx = clean_text.find("निष्कर्ष")
    if conclusion_idx != -1:
        search_text = clean_text[conclusion_idx:]
    else:
        search_text = clean_text

    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in search_text:
            return verdict

    return None


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

        soup = BeautifulSoup(html, "lxml")

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
            body_text = ""
            content_div = (
                soup.find("div", class_="article-content") or
                soup.find("div", class_="content") or
                soup.find("article") or
                soup.find("main")
            )
            if content_div:
                for tag in content_div.find_all(["script", "style", "nav"]):
                    tag.decompose()
                body_text = content_div.get_text(separator="\n", strip=True)

            # Strip leading "Shares" widget artifact — affects ~72% of articles
            body_text = strip_shares_prefix(body_text)

            if not body_text:
                self.logger.warning(f"No body text: {url}")
                return None

            # --- Author ---
            author = ""  # JS-rendered, skipped for now

            # --- Date ---
            date_published = ""
            published_date_iso = ""

            page_text = soup.get_text()
            for month in BS_MONTHS.keys():
                pattern = rf"{month}\s+[०-९\d]+,?\s+[०-९\d]{{4}}"
                match = re.search(pattern, page_text)
                if match:
                    date_published = match.group(0)
                    published_date_iso = parse_bs_date(date_published) or ""
                    break

            if not date_published:
                year_match = re.search(r"/(\d{4})/", url)
                if year_match:
                    date_published = year_match.group(1)
                    published_date_iso = f"{year_match.group(1)}-01-01"
                    self.logger.warning(f"Date fallback to year only: {url}")

            # --- Verdict ---
            raw_verdict = ""

            # Strategy 1: og:image filename
            og_image = soup.find("meta", property="og:image")
            if og_image:
                raw_verdict = extract_verdict_from_image(
                    og_image.get("content", "")
                ) or ""

            # Strategy 2: search ALL img tags for verdict keyword
            # FIXED: was only checking first img tag
            if not raw_verdict:
                for img in soup.find_all("img", src=True):
                    src = img.get("src", "")
                    result = extract_verdict_from_image(src)
                    if result:
                        raw_verdict = result
                        break

            # Strategy 3: body text conclusion section
            # FIXED: now includes झुटो, साँचो, गलत keywords
            if not raw_verdict:
                raw_verdict = extract_verdict_from_body(body_text) or ""

            if not raw_verdict:
                self.logger.warning(f"No verdict found: {url}")

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