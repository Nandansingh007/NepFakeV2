# scrapers/nepalfactcheck.py
# =============================================================================
# NepalFactCheck scraper.
# Scrapes: nepalfactcheck.org/news/page/{n}/
#
# HTML structure (verified 05 Sep 2026):
#   Listing:     WordPress — articles in <article> tags
#   URL pattern: nepalfactcheck.org/YYYY/MM/slug
#   Date:        meta article:published_time — raw ISO string stored as-is
#   Verdict:     1. SVG image filename: bhramak.svg / mithya.svg etc.
#                2. Title keyword: "भ्रामक", "मिथ्या", "गलत" etc.
#                3. Conclusion section text
#                4. Full body search
#
# Stage 1 principles:
#   - date_published stored as raw ISO string as-is
#   - published_date_iso = first 10 chars for cutoff check ONLY
#   - published_date_iso NOT stored in raw JSON
# =============================================================================

import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from schema.schema import RawArticle
from scrapers.techpana import BS_MONTHS


# =============================================================================
# VERDICT EXTRACTION
# =============================================================================

SVG_VERDICT_MAP = {
    "bhramak": "भ्रामक सूचना",
    "mithya":  "मिथ्या सूचना",
    "apusto":  "अपुष्ट सूचना",
    "sahi":    "सही सूचना",
}

VERDICT_KEYWORDS = {
    "मिथ्या सूचना": "मिथ्या सूचना",
    "भ्रामक सूचना": "भ्रामक सूचना",
    "अपुष्ट सूचना": "अपुष्ट सूचना",
    "सही सूचना":    "सही सूचना",
    "मिथ्या":       "मिथ्या सूचना",
    "भ्रामक":       "भ्रामक सूचना",
    "अपुष्ट":       "अपुष्ट सूचना",
    "सही":          "सही सूचना",
    "गलत":          "मिथ्या सूचना",
    "misleading":   "भ्रामक सूचना",
    "false":        "मिथ्या सूचना",
    "unverified":   "अपुष्ट सूचना",
    "true":         "सही सूचना",
}

BS_MONTH_NAMES = list(BS_MONTHS.keys())

CONCLUSION_MARKERS = [
    "तथ्य जाँच/निष्कर्ष",
    "निष्कर्ष",
    "तथ्य जाँच",
]


def extract_verdict_from_svg(soup: BeautifulSoup) -> Optional[str]:
    """Extract verdict from SVG image filename."""
    for img in soup.find_all("img", src=True):
        src = img.get("src", "").lower()
        for keyword, verdict in SVG_VERDICT_MAP.items():
            if keyword in src:
                return verdict
    return None


def extract_verdict_from_title(title: str) -> Optional[str]:
    """Extract verdict from article title keyword."""
    if not title:
        return None
    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in title:
            return verdict
    return None


def extract_verdict_from_conclusion(body_text: str) -> Optional[str]:
    """Extract verdict from conclusion section text."""
    if not body_text:
        return None
    search_text = body_text
    for marker in CONCLUSION_MARKERS:
        idx = body_text.find(marker)
        if idx != -1:
            search_text = body_text[idx:]
            break
    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in search_text:
            return verdict
    return None


def extract_verdict_from_body(body_text: str) -> Optional[str]:
    """Full body search — last resort."""
    if not body_text:
        return None
    for keyword, verdict in VERDICT_KEYWORDS.items():
        if keyword in body_text:
            return verdict
    return None


# =============================================================================
# NEPALFACTCHECK SCRAPER
# =============================================================================

class NepalfactcheckScraper(BaseScraper):
    """
    Scraper for NepalFactCheck Nepali fact-checks.
    nepalfactcheck.org/news/page/{n}/
    Incremental: last_published_date from last_run.json
    """

    def __init__(self):
        super().__init__("nepalfactcheck")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract article URLs from NepalFactCheck listing page.
        WordPress — articles inside <article> tags or heading tags.
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links = []

        # Strategy 1: <article> tags
        for article_tag in soup.find_all("article"):
            for a in article_tag.find_all("a", href=True):
                href = a["href"]
                if re.search(r"/\d{4}/\d{2}/", href):
                    if href.startswith("http"):
                        links.append(href)
                    else:
                        links.append(
                            urljoin("https://nepalfactcheck.org", href)
                        )

        # Strategy 2: heading tags h2/h3
        if not links:
            for tag in ["h2", "h3"]:
                for heading in soup.find_all(tag):
                    a = heading.find("a", href=True)
                    if a:
                        href = a["href"]
                        if href.startswith("http"):
                            links.append(href)
                        else:
                            links.append(
                                urljoin("https://nepalfactcheck.org", href)
                            )

        # Strategy 3: all links matching article URL pattern
        if not links:
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if (
                    re.search(r"nepalfactcheck\.org/\d{4}/\d{2}/\S+", href)
                    and href not in links
                ):
                    links.append(href)

        # Filter to article URLs only
        links = [
            l for l in links
            if re.search(r"/\d{4}/\d{2}/", l)
            and "nepalfactcheck.org" in l
            and not l.endswith("/category/")
            and not l.endswith("/tag/")
            and "?p=" not in l
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

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single NepalFactCheck article.

        Sets two date fields:
          date_published:     raw ISO string stored in JSON as-is
          published_date_iso: first 10 chars for cutoff check ONLY
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
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    title = og_title.get("content", "").strip()
                    title = title.replace(" - Nepal Factcheck", "").strip()
            if not title:
                self.logger.warning(f"No title: {url}")
                return None

            # --- Body text ---
            body_text = ""
            content_div = (
                soup.find("div", class_="entry-content") or
                soup.find("div", class_="post-content") or
                soup.find("div", class_="post-body") or
                soup.find("div", class_=re.compile(r"content|article|post", re.I)) or
                soup.find("article") or
                soup.find("main")
            )

            if content_div:
                for tag in content_div.find_all(["script", "style", "nav"]):
                    tag.decompose()
                body_text = content_div.get_text(separator="\n", strip=True)

            # Fallback — full page text
            if not body_text or len(body_text) < 100:
                for tag in soup.find_all(["header", "footer", "nav", "script", "style"]):
                    tag.decompose()
                body_text = soup.get_text(separator="\n", strip=True)

            if not body_text:
                self.logger.warning(f"No body text: {url}")
                return None

            # --- Date ---
            # date_published:     raw ISO string stored as-is
            # published_date_iso: first 10 chars for cutoff check only
            date_published = ""
            published_date_iso = ""

            # Strategy 1: article:published_time meta tag
            meta_pub = soup.find("meta", property="article:published_time")
            if meta_pub:
                dt = meta_pub.get("content", "")
                if dt:
                    date_published = dt                  # raw ISO → stored as-is
                    published_date_iso = dt[:10]         # YYYY-MM-DD → cutoff only

            # Strategy 2: URL pattern /YYYY/MM/ as fallback
            if not date_published:
                match = re.search(r"/(\d{4})/(\d{2})/", url)
                if match:
                    date_published = f"{match.group(1)}-{match.group(2)}"
                    published_date_iso = f"{match.group(1)}-{match.group(2)}-01"
                    self.logger.warning(f"Date fallback to URL pattern: {url}")

            # --- Author ---
            author = ""
            page_text = soup.get_text()

            for month in BS_MONTH_NAMES:
                idx = page_text.find(month)
                if idx > 10:
                    before = page_text[max(0, idx-80):idx].strip()
                    lines = [l.strip() for l in before.split("\n") if l.strip()]
                    if lines:
                        candidate = lines[-1]
                        if (
                            2 < len(candidate) < 50
                            and not any(c.isdigit() for c in candidate)
                            and not any(
                                skip in candidate
                                for skip in ["होम", "Home", "FAQ", "तथ्यजाँच"]
                            )
                        ):
                            author = candidate
                    break

            if not author:
                author_link = soup.find("a", rel="author")
                if author_link:
                    author = author_link.get_text(strip=True)

            # --- Verdict ---
            raw_verdict = extract_verdict_from_svg(soup)

            if not raw_verdict:
                raw_verdict = extract_verdict_from_title(title)

            if not raw_verdict:
                raw_verdict = extract_verdict_from_conclusion(body_text)

            if not raw_verdict:
                raw_verdict = extract_verdict_from_body(body_text)

            if not raw_verdict:
                self.logger.warning(f"No verdict found: {url}")

            # --- External links ---
            external_links = []
            if content_div:
                for a in content_div.find_all("a", href=True):
                    href = a["href"]
                    if (
                        href.startswith("http")
                        and "nepalfactcheck.org" not in href
                    ):
                        external_links.append(href)

            article = RawArticle(
                source_name="nepalfactcheck",
                source_url=url,
                title=title,
                body_text=body_text,
                raw_verdict_text=raw_verdict or "",
                date_published=date_published,          # raw ISO string
                published_date_iso=published_date_iso,  # cutoff only
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