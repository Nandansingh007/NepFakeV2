# scrapers/nepalcheck.py
# =============================================================================
# NepalCheck fact-check scraper.
# Scrapes: nepalcheck.org/factcheck/page/{n}/
#
# HTML structure (verified 31 Aug 2026):
#   Article cards:  <h2><a href="/YYYY/MM/DD/slug">title</a></h2>
#   URL pattern:    nepalcheck.org/YYYY/MM/DD/slug
#   Date:           meta article:published_time — clean ISO format
#   Author:         Plain text in author bio section
#   Verdict:        Written in English prose in Conclusion section
#                   No structured tag — extracted via keyword matching
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
# NepalCheck writes verdict in English prose in the Conclusion section.
# Keywords confirmed from live articles.
# =============================================================================

# Order matters — check more specific terms first
VERDICT_PATTERNS = [
    ("false",       ["is false", "are false", "is not true",
                     "found to be false", "claim is false",
                     "claims are false", "rated false"]),
    ("misleading",  ["is misleading", "are misleading",
                     "rated misleading", "found to be misleading",
                     "claim is misleading", "claims are misleading"]),
    ("half-truth",  ["half-truth", "half truth", "partially true",
                     "partly true", "partly false"]),
    ("true",        ["is true", "are true", "found to be true",
                     "claim is true", "rated true"]),
    ("unverified",  ["could not verify", "cannot verify",
                     "unable to verify", "unverified"]),
]


def extract_verdict_from_conclusion(body_text: str) -> Optional[str]:
    """
    Extract verdict from NepalCheck article conclusion section.
    NepalCheck writes verdict as English prose in a Conclusion section.

    Strategy:
        1. Find "Conclusion" section
        2. Search for verdict keyword patterns
        3. Fall back to searching full body if no conclusion found

    Args:
        body_text: Full article body text

    Returns:
        Verdict string e.g. "misleading" / "false" / "true" or None
    """
    if not body_text:
        return None

    body_lower = body_text.lower()

    # Find conclusion section
    conclusion_idx = body_lower.find("conclusion")
    search_text = (
        body_lower[conclusion_idx:]
        if conclusion_idx != -1
        else body_lower
    )

    # Search for verdict patterns
    for verdict, patterns in VERDICT_PATTERNS:
        for pattern in patterns:
            if pattern in search_text:
                return verdict

    return None


# =============================================================================
# NEPALCHECK SCRAPER
# =============================================================================

class NepalcheckScraper(BaseScraper):
    """
    Scraper for NepalCheck English fact-checks.
    nepalcheck.org/factcheck/page/{n}/
    """

    def __init__(self):
        super().__init__("nepalcheck")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract article URLs from NepalCheck listing page.
        WordPress structure: articles in <h2><a href="..."> tags.

        Args:
            page_url: Listing page URL

        Returns:
            List of absolute article URLs
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links = []

        # WordPress article links in <h2> tags
        for h2 in soup.find_all("h2"):
            a = h2.find("a", href=True)
            if a:
                href = a["href"]
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(urljoin("https://nepalcheck.org", href))

        # Filter to article URLs only
        # Pattern: nepalcheck.org/YYYY/MM/DD/slug
        links = [
            l for l in links
            if re.search(r"/\d{4}/\d{2}/\d{2}/", l)
            and "nepalcheck.org" in l
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
        """
        Extract article date from URL pattern without fetching.
        NepalCheck URL pattern: /YYYY/MM/DD/slug
        This allows cutoff check before fetching full article.

        Args:
            url: Article URL

        Returns:
            ISO date string "YYYY-MM-DD" or None
        """
        match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single NepalCheck fact-check article.

        Args:
            url: Full article URL

        Returns:
            RawArticle if successful, None if failed
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
                # Fallback to og:title
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    title = og_title.get("content", "").strip()
            if not title:
                self.logger.warning(f"No title: {url}")
                return None

            # --- Body text ---
            body_text = ""
            # WordPress content is in .entry-content or .post-content
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
            # Strategy 1: article:published_time meta tag (clean ISO format)
            date_published = ""
            meta_pub = soup.find("meta", property="article:published_time")
            if meta_pub:
                dt = meta_pub.get("content", "")
                if dt:
                    date_published = dt[:10]  # YYYY-MM-DD

            # Strategy 2: extract from URL pattern
            if not date_published:
                date_published = self.get_article_date(url) or ""

            # Strategy 3: look for date text in page
            if not date_published:
                time_tag = soup.find("time")
                if time_tag:
                    dt = time_tag.get("datetime", "")
                    if dt:
                        date_published = dt[:10]

            # --- Author ---
            author = ""
            # NepalCheck shows author name in article bio section
            # "This article is written by [Name]"
            page_text = soup.get_text()
            written_by = re.search(
                r"This article is written by\s+(.+?)(?:\n|$)",
                page_text
            )
            if written_by:
                author = written_by.group(1).strip()

            # Fallback: look for author meta tag
            if not author:
                meta_author = soup.find("meta", attrs={"name": "author"})
                if meta_author:
                    author = meta_author.get("content", "").strip()

            # --- Verdict ---
            # NepalCheck writes verdict in English prose
            # Must extract from Conclusion section
            raw_verdict = extract_verdict_from_conclusion(body_text)
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
                f"date: {date_published} | "
                f"author: {author}"
            )
            return article

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None