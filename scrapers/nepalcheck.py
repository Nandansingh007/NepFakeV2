# scrapers/nepalcheck.py
# =============================================================================
# NepalCheck Nepali fact-check scraper.
# Scrapes: np.nepalcheck.org/factcheck/page/{n}/
#
# CHANGED 01 Sep 2026:
#   URL changed from nepalcheck.org (English) to np.nepalcheck.org (Nepali)
#   Verdict extraction changed from English prose to Nepali keywords
#   Verdict appears in article title and body — not English conclusion prose
#
# HTML structure (verified 01 Sep 2026):
#   Article cards:  <h2><a href="/YYYY/MM/DD/slug">title</a></h2>
#   URL pattern:    np.nepalcheck.org/YYYY/MM/DD/slug
#   Date:           meta article:published_time — clean ISO format
#   Verdict:        Nepali keyword in title e.g. "दाबी भ्रामक"
#                   Fallback: body conclusion section
#   Pagination:     /factcheck/page/{n}/
# =============================================================================

import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from schema.schema import RawArticle


# =============================================================================
# VERDICT EXTRACTION
# np.nepalcheck.org uses Nepali verdict keywords in title and body
# =============================================================================

# CHANGED: Nepali keywords instead of English prose patterns
VERDICT_KEYWORDS = {
    "मिथ्या": "मिथ्या",
    "भ्रामक": "भ्रामक",
    "अपुष्ट": "अपुष्ट",
    "सही":    "सही",
    "गलत":    "मिथ्या",   # variant — maps to same label
}

# Conclusion section markers in Nepali
CONCLUSION_MARKERS = ["निष्कर्ष", "तथ्य जाँच", "निर्क्योल", "सत्यापन"]


def extract_verdict(title: str, body_text: str) -> Optional[str]:
    """
    Extract verdict from article title and body.
    np.nepalcheck.org includes verdict keyword in article title.

    Strategy:
        1. Search title first — most reliable
        2. Search conclusion section in body
        3. Search full body as fallback

    Args:
        title:     Article headline
        body_text: Full article body text

    Returns:
        Nepali verdict string or None
    """
    # Strategy 1: title contains verdict keyword (most reliable)
    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in title:
            return verdict

    # Strategy 2: conclusion section in body
    search_text = body_text
    for marker in CONCLUSION_MARKERS:
        idx = body_text.find(marker)
        if idx != -1:
            search_text = body_text[idx:]
            break

    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in search_text:
            return verdict

    # Strategy 3: full body search as last resort
    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in body_text:
            return verdict

    return None


# =============================================================================
# NEPALCHECK SCRAPER
# =============================================================================

class NepalcheckScraper(BaseScraper):
    """
    Scraper for NepalCheck Nepali fact-checks.
    np.nepalcheck.org/factcheck/page/{n}/
    """

    def __init__(self):
        super().__init__("nepalcheck")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract article URLs from np.nepalcheck.org listing page.
        WordPress structure: articles in <h2><a href="..."> tags.
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links = []

        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if a:
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                else:
                    # CHANGED: base URL updated to np.nepalcheck.org
                    links.append(urljoin("https://np.nepalcheck.org", href))

        # CHANGED: filter updated to np.nepalcheck.org
        links = [
            l for l in links
            if re.search(r"/\d{4}/\d{2}/\d{2}/", l)
            and "np.nepalcheck.org" in l
        ]

        # Deduplicate preserving order
        seen = set()
        unique_links = []
        for l in links:
            if l not in seen:
                seen.add(l)
                unique_links.append(l)

        self.logger.debug(
            f"Found {len(unique_links)} article links on {page_url}"
        )
        return unique_links

    def get_article_date(self, url: str) -> Optional[str]:
        """Extract date from URL pattern /YYYY/MM/DD/ without fetching."""
        match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """Scrape a single np.nepalcheck.org fact-check article."""
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
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    title = og_title.get("content", "").strip()
            if not title:
                self.logger.warning(f"No title: {url}")
                return None

            # --- Body text ---
            body_text = ""
            content_div = (
                soup.find("div", class_="entry-content") or
                soup.find("div", class_="post-content") or
                soup.find("div", class_="wp-block-group") or
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

            # --- Date ---
            date_published = ""
            meta_pub = soup.find("meta", property="article:published_time")
            if meta_pub:
                dt = meta_pub.get("content", "")
                if dt:
                    date_published = dt[:10]

            if not date_published:
                date_published = self.get_article_date(url) or ""

            if not date_published:
                time_tag = soup.find("time")
                if time_tag:
                    dt = time_tag.get("datetime", "")
                    if dt:
                        date_published = dt[:10]

            # --- Author ---
            author = ""
            meta_author = soup.find("meta", attrs={"name": "author"})
            if meta_author:
                author = meta_author.get("content", "").strip()

            # --- Verdict ---
            # CHANGED: Nepali keyword extraction instead of English prose
            raw_verdict = extract_verdict(title, body_text)
            if not raw_verdict:
                self.logger.warning(f"No verdict found: {url}")

            # --- External links ---
            external_links = []
            if content_div:
                for a in content_div.find_all("a", href=True):
                    href = a["href"]
                    if (
                        href.startswith("http")
                        and "nepalcheck.org" not in href
                        and "wordpress.com" not in href
                    ):
                        external_links.append(href)

            article = RawArticle(
                source_name="nepalcheck",
                source_url=url,
                title=title,
                body_text=body_text,
                raw_verdict_text=raw_verdict or "",
                date_published=date_published,
                date_scraped=date.today().isoformat(),
                author=author,
                category="factcheck",
                external_links=external_links[:20],
            )

            self.logger.debug(
                f"Scraped: {title[:60]} | "
                f"verdict: {raw_verdict} | "
                f"date: {date_published}"
            )
            return article

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None