# scrapers/base.py
# =============================================================================
# BaseScraper — parent class for all NepFakeV2 scrapers.
#
# Incremental strategy:
#   - Tracks last_published_date per source in last_run.json
#   - Each article has published_date_iso for cutoff comparison
#   - Cutoff: article.published_date_iso <= last_published_date → STOP
#   - After run: max(published_date_iso) saved as new last_published_date
#
# Stage 1 principle:
#   - Store everything as-is from website
#   - published_date_iso is internal only — NOT stored in raw JSON
#
# Proxy strategy:
#   - TechPana blocked by GitHub Actions IP (AWS datacenter)
#   - Cloudflare Worker proxy used when CLOUDFLARE_WORKER_URL env set
#   - Local runs use direct requests (residential IP works fine)
# =============================================================================

import json
import os
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


class BaseScraper(ABC):
    """
    Abstract base class for all NepFakeV2 scrapers.
    Subclasses must implement:
        - get_article_links(page_url) → list[str]
        - scrape_article(url) → RawArticle
    """

    def __init__(self, source_name: str):
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
        self.articles_scraped = 0
        self.articles_skipped = 0

        # Load cutoff from last_run.json
        self.last_published_date = self._load_last_published_date()

        self.logger.info(
            f"Initialized {source_name} scraper — "
            f"last_published_date: {self.last_published_date}"
        )

    # -------------------------------------------------------------------------
    # HTTP SESSION
    # -------------------------------------------------------------------------

    def _build_session(self) -> requests.Session:
        """
        Build requests Session with browser-like headers.
        Browser headers prevent basic bot detection.
        Cloudflare Worker proxy handled in fetch_page().
        """
        session = requests.Session()

        # CHANGED: full browser headers instead of bot user agent
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ne-NP,ne;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })

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
    # INCREMENTAL — LOAD LAST PUBLISHED DATE
    # -------------------------------------------------------------------------

    def _load_last_published_date(self) -> Optional[str]:
        """
        Load last_published_date for this source from last_run.json.
        Returns None if first run — scrape everything.
        Returns ISO date string "YYYY-MM-DD" if previous run exists.
        """
        if not LAST_RUN_FILE.exists():
            self.logger.info("No last_run.json — first run, scraping all")
            return None

        try:
            with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
                last_run = json.load(f)

            source_data = last_run.get("sources", {}).get(self.source_name, {})
            last_published = source_data.get("last_published_date")

            if not last_published:
                self.logger.info(
                    f"No last_published_date for {self.source_name} — scraping all"
                )
                return None

            self.logger.info(
                f"last_published_date: {last_published} — "
                f"only scraping articles published after this date"
            )
            return last_published

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.logger.warning(
                f"Could not read last_run.json: {e} — scraping all"
            )
            return None

    # -------------------------------------------------------------------------
    # INCREMENTAL — CUTOFF CHECK
    # -------------------------------------------------------------------------

    def is_before_cutoff(self, published_date_iso: str) -> bool:
        """
        Check if article is old (should be skipped).

        Args:
            published_date_iso: ISO date "YYYY-MM-DD" from article

        Returns:
            True  → article is old, stop pagination
            False → article is new, scrape it
        """
        if not self.last_published_date:
            return False

        if not published_date_iso:
            return False

        return published_date_iso <= self.last_published_date

    # -------------------------------------------------------------------------
    # HTTP REQUEST
    # -------------------------------------------------------------------------

    def fetch_page(self, url: str) -> Optional[str]:
        """
        Fetch page HTML.
        TechPana: uses ZenRows API to bypass Cloudflare bot protection.
        All other sources: direct request.
        """
        try:
            zenrows_key = os.environ.get("ZENROWS_API_KEY")

            if zenrows_key and "techpana.com" in url:
                self.logger.debug(f"ZenRows fetch: {url}")
                from zenrows import ZenRowsClient
                client = ZenRowsClient(zenrows_key)
                response = client.get(
                    url,
                    params={
                        "js_render": "true",
                        "premium_proxy": "true",
                        "wait": "3000",
                    }
                )
            else:
                self.logger.debug(f"Direct fetch: {url}")
                response = self.session.get(url, timeout=REQUEST_TIMEOUT)

            response.raise_for_status()
            response.encoding = "utf-8"
            time.sleep(self.config["rate_limit_seconds"])
            return response.text

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 503:
                self.logger.warning(f"503 rate limit: {url} — skipping")
            else:
                self.logger.error(f"HTTP error fetching {url}: {e}")
            return None
        except requests.exceptions.ReadTimeout:
            self.logger.warning(f"Read timeout: {url} — skipping")
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error fetching {url}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"ZenRows error fetching {url}: {e}")
            return None

    # -------------------------------------------------------------------------
    # SAVE RAW OUTPUT
    # -------------------------------------------------------------------------

    def save_raw(self, articles: list[RawArticle]) -> Path:
        """
        Save scraped articles to dated JSON file.
        published_date_iso is NOT saved — internal field only.
        Deduplicates by source_url within same run.
        """
        today = date.today().strftime("%Y-%m-%d")
        output_path = self.raw_dir / f"{today}.json"

        existing = []
        if output_path.exists():
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            self.logger.info(
                f"Appending to existing file: {output_path.name} "
                f"({len(existing)} existing articles)"
            )

        new_records = [self._article_to_dict(a) for a in articles]

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
        """
        Convert RawArticle to dict for JSON storage.
        published_date_iso intentionally excluded — internal only.
        """
        return {
            "source_name":      article.source_name,
            "source_url":       article.source_url,
            "title":            article.title,
            "body_text":        article.body_text,
            "raw_verdict_text": article.raw_verdict_text,
            "date_published":   article.date_published,
            "date_scraped":     article.date_scraped,
            "author":           article.author,
            "category":         article.category,
            "external_links":   article.external_links,
            "annotator_notes":  article.annotator_notes,
        }

    # -------------------------------------------------------------------------
    # FIND MAX PUBLISHED DATE
    # -------------------------------------------------------------------------

    def get_max_published_date(self, articles: list[RawArticle]) -> Optional[str]:
        """
        Find the maximum published_date_iso from scraped articles.
        Used by collector.py to update last_published_date in last_run.json.
        """
        dates = [
            a.published_date_iso
            for a in articles
            if a.published_date_iso
        ]
        if not dates:
            return None
        return max(dates)

    # -------------------------------------------------------------------------
    # PAGINATION
    # -------------------------------------------------------------------------

    def paginate(self) -> list[RawArticle]:
        """
        Paginate through all pages until:
        1. Empty page — end of site
        2. Article published_date_iso <= last_published_date — cutoff reached
        3. WordPress redirect loop detected
        """
        all_articles = []
        page = self.config["start_page"]
        stop = False
        seen_page_urls = set()

        while not stop:
            page_url = self.config["list_url_template"].format(page=page)
            self.logger.info(f"Scraping page {page}: {page_url}")

            links = self.get_article_links(page_url)

            if not links:
                self.logger.info(
                    f"Page {page} returned no articles — stopping"
                )
                break

            new_links = [l for l in links if l not in seen_page_urls]
            if not new_links:
                self.logger.info(
                    f"Page {page} — WordPress redirect loop detected, stopping"
                )
                break

            seen_page_urls.update(links)

            page_articles = []
            for url in new_links:

                article = self.scrape_article(url)

                if article is None:
                    self.articles_skipped += 1
                    continue

                if self.is_before_cutoff(article.published_date_iso):
                    self.logger.info(
                        f"Cutoff reached — article date "
                        f"{article.published_date_iso} <= "
                        f"{self.last_published_date} — stopping"
                    )
                    stop = True
                    break

                page_articles.append(article)
                self.articles_scraped += 1

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
    # ABSTRACT METHODS
    # -------------------------------------------------------------------------

    @abstractmethod
    def get_article_links(self, page_url: str) -> list[str]:
        """Extract article URLs from a listing page."""
        pass

    @abstractmethod
    def scrape_article(self, url: str) -> Optional[RawArticle]:
        """
        Scrape a single article.
        Must set article.published_date_iso for cutoff check.
        Must set article.date_published as raw string for storage.
        """
        pass

    # -------------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -------------------------------------------------------------------------

    def run(self) -> list[RawArticle]:
        """Main entry point. Called by collector.py."""
        self.logger.info(f"Starting {self.source_name} scraper")
        articles = self.paginate()

        if articles:
            self.save_raw(articles)
        else:
            self.logger.info(f"No new articles found for {self.source_name}")

        return articles