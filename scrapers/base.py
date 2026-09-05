# scrapers/base.py
# =============================================================================
# BaseScraper — parent class for all NepFakeV2 scrapers.
# Every source-specific scraper inherits from this class.
#
# Provides:
#   - Rate limiting between requests
#   - Retry logic with exponential backoff
#   - Incremental scraping via date cutoff
#   - Raw JSON saving with dated filenames
#   - Structured logging per scraper
#   - Shared HTTP session with correct headers
#   - WordPress redirect loop detection
#
# Usage:
#   from scrapers.base import BaseScraper
#   class TechpanaScraper(BaseScraper):
#       def scrape(self): ...
# =============================================================================

import json
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import (
    ACTIVE_SOURCES,
    RAW_DIRS,
    LAST_RUN_FILE,
    USER_AGENT,
    REQUEST_TIMEOUT,
)
from schema.schema import RawArticle


# =============================================================================
# BASE SCRAPER
# =============================================================================

class BaseScraper(ABC):
    """
    Abstract base class for all NepFakeV2 scrapers.
    Subclasses must implement:
        - scrape_article(url) → RawArticle
        - get_article_links(page_url) → list[str]
        - get_article_date(url) → str
    """

    def __init__(self, source_name: str):
        """
        Initialize scraper for a given source.

        Args:
            source_name: Key from sources.yaml e.g. "techpana"
        """
        if source_name not in ACTIVE_SOURCES:
            raise ValueError(
                f"Source '{source_name}' not found in active sources. "
                f"Check sources.yaml."
            )

        self.source_name = source_name
        self.config = ACTIVE_SOURCES[source_name]
        self.logger = logging.getLogger(f"nepfakev2.{source_name}")
        self.raw_dir = RAW_DIRS[source_name]
        self.session = self._build_session()
        self.cutoff_date = self._get_cutoff_date()
        self.articles_scraped = 0
        self.articles_skipped = 0

        self.logger.info(
            f"Initialized {source_name} scraper — "
            f"cutoff date: {self.cutoff_date}"
        )

    # -------------------------------------------------------------------------
    # HTTP SESSION
    # -------------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """
        Build a requests Session with:
        - Correct headers including user agent
        - Automatic retry on connection errors
        """
        session = requests.Session()

        session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "ne, en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })

        # Retry on connection errors and 5xx responses
        # Does NOT retry on 4xx — those are our fault
        retry = Retry(
            total=self.config["retry_attempts"],
            backoff_factor=self.config["retry_backoff_seconds"],
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    # -------------------------------------------------------------------------
    # INCREMENTAL SCRAPING — DATE CUTOFF
    # -------------------------------------------------------------------------

    def _get_cutoff_date(self) -> Optional[date]:
        """
        Get the cutoff date for incremental scraping.
        Returns the date of the last successful scrape for this source.
        Returns None if this is the first run (scrape everything).
        """
        if not LAST_RUN_FILE.exists():
            self.logger.info("No last_run.json found — first run, scraping all articles")
            return None

        try:
            with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
                last_run = json.load(f)

            source_data = last_run.get("sources", {}).get(self.source_name, {})
            last_run_date_str = source_data.get("last_run_date")

            if not last_run_date_str:
                self.logger.info(f"No previous run found for {self.source_name} — scraping all")
                return None

            cutoff = datetime.strptime(last_run_date_str, "%Y-%m-%d").date()
            self.logger.info(f"Cutoff date: {cutoff} — only scraping articles after this date")
            return cutoff

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(f"Could not read last_run.json: {e} — scraping all articles")
            return None

    def is_before_cutoff(self, article_date_str: str) -> bool:
        """
        Check if an article date is before the cutoff date.
        If True, stop pagination — we have seen this article before.

        Args:
            article_date_str: ISO format date string "YYYY-MM-DD"

        Returns:
            True if article is older than cutoff (should stop)
            False if article is new (should scrape)
        """
        if self.cutoff_date is None:
            return False  # No cutoff — scrape everything

        try:
            article_date = datetime.strptime(article_date_str, "%Y-%m-%d").date()
            return article_date <= self.cutoff_date
        except ValueError:
            self.logger.warning(f"Could not parse article date: {article_date_str} — scraping anyway")
            return False

    # -------------------------------------------------------------------------
    # HTTP REQUEST
    # -------------------------------------------------------------------------

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch a page and return its HTML content.
        Handles rate limiting and errors.

        Args:
            url: URL to fetch

        Returns:
            HTML string if successful, None if failed
        """
        try:
            self.logger.debug(f"Fetching: {url}")
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            response.encoding = "utf-8"

            # Rate limiting — wait between requests
            time.sleep(self.config["rate_limit_seconds"])

            return response.text

        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error fetching {url}: {e}")
            return None

        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error fetching {url}: {e}")
            return None

        except requests.exceptions.Timeout:
            self.logger.error(f"Timeout fetching {url}")
            return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return None

    # -------------------------------------------------------------------------
    # SAVE RAW OUTPUT
    # -------------------------------------------------------------------------

    def save_raw(self, articles: list[RawArticle]) -> Path:
        """
        Save scraped articles to a dated JSON file.
        File is immutable once written — never overwrite.

        Args:
            articles: List of RawArticle to save

        Returns:
            Path to saved file
        """
        today = date.today().strftime("%Y-%m-%d")
        output_path = self.raw_dir / f"{today}.json"

        # If file exists for today (re-run) — append new articles
        existing = []
        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            self.logger.info(
                f"Appending to existing file: {output_path.name} "
                f"({len(existing)} existing articles)"
            )

        # Convert dataclasses to dicts
        new_records = [self._article_to_dict(a) for a in articles]

        # Merge and deduplicate by source_url
        all_records = existing + new_records
        seen_urls = set()
        deduplicated = []
        for record in all_records:
            if record["source_url"] not in seen_urls:
                seen_urls.add(record["source_url"])
                deduplicated.append(record)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(deduplicated, f, ensure_ascii=False, indent=2)

        self.logger.info(
            f"Saved {len(articles)} new articles → {output_path} "
            f"({len(deduplicated)} total)"
        )
        return output_path

    def _article_to_dict(self, article: RawArticle) -> dict:
        """Convert RawArticle dataclass to dict for JSON serialization."""
        return {
            "source_name":       article.source_name,
            "source_url":        article.source_url,
            "title":             article.title,
            "body_text":         article.body_text,
            "raw_verdict_text":  article.raw_verdict_text,
            "date_published":    article.date_published,
            "date_scraped":      article.date_scraped,
            "author":            article.author,
            "category":          article.category,
            "external_links":    article.external_links,
        }

    # -------------------------------------------------------------------------
    # PAGINATION
    # -------------------------------------------------------------------------

    def paginate(self) -> list[RawArticle]:
        """
        Paginate through all pages of the source until:
        1. Empty page found (end of site)
        2. Article date is before cutoff (incremental stop)
        3. Request fails after all retries
        4. Same URLs returned as previous page (WordPress redirect loop)

        Returns:
            List of all new RawArticle found
        """
        all_articles = []
        page = self.config["start_page"]
        stop = False
        seen_page_urls = set()  # tracks all article URLs seen so far

        while not stop:
            page_url = self.config["list_url_template"].format(page=page)
            self.logger.info(f"Scraping page {page}: {page_url}")

            # Get article links from this page
            links = self.get_article_links(page_url)

            # Stop condition 1: empty page = end of site
            if not links:
                self.logger.info(
                    f"Page {page} returned no articles — stopping pagination"
                )
                break

            # Stop condition 2: WordPress redirect loop detection
            # If ALL links on this page were already seen in previous pages
            # the site is redirecting out-of-range pages back to page 1
            new_links = [l for l in links if l not in seen_page_urls]
            if not new_links:
                self.logger.info(
                    f"Page {page} returned only previously seen URLs — "
                    f"WordPress redirect loop detected, stopping pagination"
                )
                break

            # Register all links from this page as seen
            seen_page_urls.update(links)

            # Scrape each new article
            page_articles = []
            for url in new_links:
                # Check date before fetching full article
                article_date = self.get_article_date(url)
                if article_date and self.is_before_cutoff(article_date):
                    self.logger.info(
                        f"Article date {article_date} is before cutoff "
                        f"{self.cutoff_date} — stopping pagination"
                    )
                    stop = True
                    break

                article = self.scrape_article(url)
                if article:
                    page_articles.append(article)
                    self.articles_scraped += 1
                else:
                    self.articles_skipped += 1

            all_articles.extend(page_articles)
            self.logger.info(
                f"Page {page}: scraped {len(page_articles)} articles "
                f"(total so far: {len(all_articles)})"
            )

            page += 1

        self.logger.info(
            f"{self.source_name} complete — "
            f"scraped: {self.articles_scraped}, "
            f"skipped: {self.articles_skipped}"
        )
        return all_articles

    # -------------------------------------------------------------------------
    # ABSTRACT METHODS — implemented by each source scraper
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_article_links(self, page_url: str) -> list[str]:
        """
        Extract all article URLs from a listing page.

        Args:
            page_url: URL of the listing/index page

        Returns:
            List of absolute article URLs
        """
        pass

    @abstractmethod
    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single article page and return a RawArticle.

        Args:
            url: URL of the article page

        Returns:
            RawArticle if successful, None if failed
        """
        pass

    @abstractmethod
    def get_article_date(self, url: str) -> Optional[str]:
        """
        Get the publication date of an article without
        fully scraping it. Used for cutoff date checking
        during pagination — avoids fetching full articles
        we don't need.

        Args:
            url: URL of the article page

        Returns:
            ISO format date string "YYYY-MM-DD" or None
        """
        pass

    # -------------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -------------------------------------------------------------------------

    def run(self) -> list[RawArticle]:
        """
        Main entry point. Called by collector.py.
        Paginates, scrapes, saves raw output.

        Returns:
            List of scraped RawArticle
        """
        self.logger.info(f"Starting {self.source_name} scraper")
        articles = self.paginate()

        if articles:
            self.save_raw(articles)
        else:
            self.logger.info(f"No new articles found for {self.source_name}")

        return articles