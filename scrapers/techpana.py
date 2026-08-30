# scrapers/techpana.py
# =============================================================================
# TechPana fact-check scraper.
# Scrapes: techpana.com/factcheck/?tab=nepali&page={n}
#
# HTML structure (verified 31 Aug 2026):
#   Article cards: <h3><a href="/2026/XXXXXX/slug">title</a></h3>
#   Author:        <a href="/author/NN">Author Name</a>
#   Date:          Plain text after author — "भदौ ९, २०८३ १६:८"
#   Verdict:       og:image filename e.g. "False_xxx.jpg"
#   Pagination:    ?tab=nepali&page={n}
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
# NEPALI BIKRAM SAMBAT → ISO DATE CONVERTER
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
    Parse Nepali BS date string to exact ISO format.
    Uses nepali-datetime library.

    Examples:
        "भदौ ९, २०८३"   → "2026-08-25"
        "साउन २८, २०८३" → "2026-08-13"
    """
    try:
        date_str = date_str.strip()
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


# =============================================================================
# VERDICT EXTRACTION
# =============================================================================

VERDICT_KEYWORDS = {
    "मिथ्या": "मिथ्या",
    "भ्रामक": "भ्रामक",
    "अपुष्ट": "अपुष्ट",
    "सही":    "सही",
}

IMAGE_VERDICT_MAP = {
    "false":      "मिथ्या",
    "misleading": "भ्रामक",
    "unverified": "अपुष्ट",
    "verified":   "सही",
}


def extract_verdict_from_image(img_url: str) -> Optional[str]:
    if not img_url:
        return None
    img_lower = img_url.lower()
    for keyword, verdict in IMAGE_VERDICT_MAP.items():
        if keyword in img_lower:
            return verdict
    return None


def extract_verdict_from_body(body_text: str) -> Optional[str]:
    if not body_text:
        return None
    conclusion_idx = body_text.find("निष्कर्ष")
    search_text = body_text[conclusion_idx:] if conclusion_idx != -1 else body_text
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
    """

    def __init__(self):
        super().__init__("techpana")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract Nepali fact-check article URLs from listing page.
        Excludes English articles.
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links = []

        for h3 in soup.find_all("h3"):
            a = h3.find("a", href=True)
            if a:
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(urljoin("https://techpana.com", href))

        # Keep only fact-check article URLs, exclude English
        links = [
            l for l in links
            if re.search(r"/\d{4}/\d+/", l)
            and "factcheck_eng" not in l
            and "/english/" not in l
        ]

        # Deduplicate preserving order
        seen = set()
        unique_links = []
        for l in links:
            if l not in seen:
                seen.add(l)
                unique_links.append(l)

        self.logger.debug(
            f"Found {len(unique_links)} Nepali article links on {page_url}"
        )
        return unique_links

    def get_article_date(self, url: str) -> Optional[str]:
        """Date extracted inside scrape_article()."""
        return None

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """Scrape a single TechPana fact-check article."""
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
            if not body_text:
                self.logger.warning(f"No body text: {url}")
                return None

            # --- Author ---
            # Structure: <a href="/author/77">रञ्जिता उप्रेती</a>
            author = ""
            author_link = soup.find("a", href=re.compile(r"/author/\d+"))
            if author_link:
                author = author_link.get_text(strip=True)

            # --- Date ---
            # Strategy 1: article:published_time meta tag
            date_published = ""
            meta_pub = soup.find("meta", property="article:published_time")
            if meta_pub:
                dt = meta_pub.get("content", "")
                if dt:
                    date_published = dt[:10]

            # Strategy 2: Nepali month name pattern in page text
            if not date_published:
                page_text = soup.get_text()
                for month in BS_MONTHS.keys():
                    pattern = rf"{month}\s+[०-९\d]+,?\s+[०-९\d]{{4}}"
                    match = re.search(pattern, page_text)
                    if match:
                        date_published = parse_bs_date(match.group(0)) or ""
                        break

            # Strategy 3: year from URL as last resort
            if not date_published:
                year_match = re.search(r"/(\d{4})/", url)
                if year_match:
                    date_published = f"{year_match.group(1)}-01-01"
                    self.logger.warning(
                        f"Date fallback to year for: {url}"
                    )

            # --- Verdict ---
            # Strategy 1: og:image filename
            raw_verdict = ""
            og_image = soup.find("meta", property="og:image")
            if og_image:
                raw_verdict = extract_verdict_from_image(
                    og_image.get("content", "")
                ) or ""

            # Strategy 2: any img src with verdict keyword
            if not raw_verdict:
                img_tag = soup.find(
                    "img",
                    src=re.compile(
                        r"(false|misleading|unverified|verified)", re.I
                    )
                )
                if img_tag:
                    raw_verdict = extract_verdict_from_image(
                        img_tag.get("src", "")
                    ) or ""

            # Strategy 3: body text conclusion section
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
                date_scraped=date.today().isoformat(),
                author=author,
                category="factcheck",
                external_links=external_links[:20],
            )

            self.logger.debug(
                f"Scraped: {title[:60]} | "
                f"verdict: {raw_verdict} | "
                f"date: {date_published} | "
                f"author: {author}"
            )
            return article

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None