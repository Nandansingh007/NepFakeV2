# scrapers/bbc_nepali.py
# =============================================================================
# BBC Nepali news scraper.
# Scrapes: bbc.com/nepali
#
# HTML structure (verified from known BBC patterns):
#   Homepage:    bbc.com/nepali
#   Articles:    bbc.com/nepali/articles/SLUG
#   Date:        <time datetime="YYYY-MM-DDTHH:MM:SS"> tag
#   Author:      Byline section — may be JS-rendered
#   Body:        <article> tag, paragraphs in <p> tags
#   Label:       0 (REAL) — assigned by source type, not verdict tag
#   Pagination:  Homepage loads more via JS — scrape homepage + topic pages
# =============================================================================

import re
from datetime import date
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from schema.schema import RawArticle


# BBC Nepali topic pages — used as additional listing sources
# These are static HTML pages that load article links
BBC_TOPIC_PAGES = [
    "https://www.bbc.com/nepali",
    "https://www.bbc.com/nepali/topics/c340r0ljlqyt",  # Nepal
    "https://www.bbc.com/nepali/topics/cz74k717k9pt",  # World
]


class BBCNepaliScraper(BaseScraper):
    """
    Scraper for BBC Nepali news articles.
    Label 0 (REAL) — presumed factual by source credibility.
    """

    def __init__(self):
        super().__init__("bbc_nepali")
        self.base_url = self.config["base_url"]

    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract BBC Nepali article URLs from a page.
        BBC article URLs follow pattern: /nepali/articles/SLUG

        Args:
            page_url: URL of page to scrape

        Returns:
            List of absolute article URLs
        """
        html = self.fetch_page(page_url)
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        links = []

        # BBC article links pattern: /nepali/articles/SLUG
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/nepali/articles/" in href:
                if href.startswith("http"):
                    links.append(href)
                else:
                    links.append(urljoin("https://www.bbc.com", href))

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
        BBC article dates cannot be extracted from URL.
        Returns None — date extracted in scrape_article().
        """
        return None

    def paginate(self) -> list[RawArticle]:
        """
        Override paginate() for BBC Nepali.
        BBC doesn't have standard pagination — scrape homepage
        and topic pages instead.

        Returns:
            List of scraped RawArticle
        """
        all_articles = []
        all_links = set()

        # Collect links from all topic pages
        for topic_url in BBC_TOPIC_PAGES:
            self.logger.info(f"Collecting links from: {topic_url}")
            links = self.get_article_links(topic_url)
            all_links.update(links)

        self.logger.info(f"Total unique BBC links found: {len(all_links)}")

        # Scrape each article
        for url in all_links:
            # Check date for cutoff
            article = self.scrape_article(url)
            if article:
                # Check cutoff after scraping
                if article.date_published and self.is_before_cutoff(
                    article.date_published
                ):
                    self.logger.debug(
                        f"Article before cutoff: {article.date_published} — skipping"
                    )
                    self.articles_skipped += 1
                    continue
                all_articles.append(article)
                self.articles_scraped += 1
            else:
                self.articles_skipped += 1

        self.logger.info(
            f"BBC Nepali complete — "
            f"scraped: {self.articles_scraped}, "
            f"skipped: {self.articles_skipped}"
        )
        return all_articles

    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single BBC Nepali article.
        Label 0 assigned by source type — no verdict extraction needed.

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
                og_title = soup.find("meta", property="og:title")
                if og_title:
                    title = og_title.get("content", "").strip()
            if not title:
                self.logger.warning(f"No title: {url}")
                return None

            # Filter out non-news pages
            # BBC Nepali has radio pages, about pages etc.
            if any(skip in url for skip in [
                "/bbc_nepali_radio/",
                "/institutional-",
                "/sport/",
            ]):
                self.logger.debug(f"Skipping non-news page: {url}")
                return None

            # --- Body text ---
            body_text = ""

            # BBC uses data-component="text-block" for article paragraphs
            text_blocks = soup.find_all(
                attrs={"data-component": "text-block"}
            )
            if text_blocks:
                body_text = "\n".join(
                    block.get_text(separator="\n", strip=True)
                    for block in text_blocks
                )

            # Fallback: article tag
            if not body_text:
                article_tag = soup.find("article")
                if article_tag:
                    for tag in article_tag.find_all(["script", "style"]):
                        tag.decompose()
                    body_text = article_tag.get_text(
                        separator="\n", strip=True
                    )

            # Fallback: main tag
            if not body_text:
                main_tag = soup.find("main")
                if main_tag:
                    for tag in main_tag.find_all(["script", "style", "nav"]):
                        tag.decompose()
                    body_text = main_tag.get_text(separator="\n", strip=True)

            if not body_text or len(body_text) < 100:
                self.logger.warning(f"No body text: {url}")
                return None

            # --- Date ---
            date_published = ""

            # Strategy 1: <time datetime="..."> tag
            time_tag = soup.find("time", attrs={"datetime": True})
            if time_tag:
                dt = time_tag.get("datetime", "")
                if dt:
                    date_published = dt[:10]  # YYYY-MM-DD

            # Strategy 2: article:published_time meta
            if not date_published:
                meta_pub = soup.find(
                    "meta", property="article:published_time"
                )
                if meta_pub:
                    dt = meta_pub.get("content", "")
                    if dt:
                        date_published = dt[:10]

            # Strategy 3: og:article:published_time
            if not date_published:
                meta_pub2 = soup.find(
                    "meta",
                    attrs={"name": "article:published_time"}
                )
                if meta_pub2:
                    date_published = meta_pub2.get("content", "")[:10]

            # --- Author ---
            # BBC byline — may be JS-rendered
            author = ""
            author_tag = soup.find(
                attrs={"data-component": "byline-block"}
            )
            if author_tag:
                author = author_tag.get_text(strip=True)

            # Fallback: rel=author
            if not author:
                author_link = soup.find("a", rel="author")
                if author_link:
                    author = author_link.get_text(strip=True)

            # --- External links ---
            external_links = []
            article_tag = soup.find("article") or soup.find("main")
            if article_tag:
                for a in article_tag.find_all("a", href=True):
                    href = a["href"]
                    if (
                        href.startswith("http")
                        and "bbc.com" not in href
                    ):
                        external_links.append(href)

            article = RawArticle(
                source_name="bbc_nepali",
                source_url=url,
                title=title,
                body_text=body_text,
                raw_verdict_text="",      # No verdict — Label 0 by source
                date_published=date_published,
                date_scraped=date.today().isoformat(),
                author=author,
                category="news",
                external_links=external_links[:20],
            )

            self.logger.debug(
                f"Scraped: {title[:60]} | "
                f"date: {date_published} | "
                f"author: {author}"
            )
            return article

        except Exception as e:
            self.logger.error(f"Error scraping {url}: {e}")
            return None