# pipeline/collector.py
# =============================================================================
# NepFakeV2 Stage 1 Orchestrator.
# Runs all active scrapers incrementally and updates state.
#
# Incremental strategy:
#   - Reads last_published_date per source from last_run.json
#   - Passes to scraper via BaseScraper._load_last_published_date()
#   - After run: saves max(published_date_iso) as new last_published_date
#
# Usage:
#   python -m pipeline.collector
#   (called by GitHub Actions weekly_scrape.yml)
# =============================================================================

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (
    ACTIVE_SOURCES,
    RAW_DIR,
    RAW_DIRS,
    LAST_RUN_FILE,
    setup_logging,
    create_directories,
)


# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def load_last_run() -> dict:
    """
    Load last run state from last_run.json.
    Returns empty state if file doesn't exist.
    """
    if not LAST_RUN_FILE.exists():
        return {
            "last_run_date": None,
            "run_id": None,
            "sources": {}
        }
    with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_last_run(state: dict) -> None:
    """Save run state to last_run.json."""
    LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# =============================================================================
# RAW STATS
# =============================================================================

def compute_raw_stats() -> dict:
    """
    Compute statistics from all raw JSON files.
    Called after every scrape run to update stats_raw.json.
    Handles both raw BS date strings and ISO date strings.
    """
    stats = {
        "total_raw_articles": 0,
        "by_source": {},
    }

    for source_name, raw_dir in RAW_DIRS.items():
        raw_dir = Path(raw_dir)
        if not raw_dir.exists():
            continue

        all_articles = []
        for json_file in sorted(raw_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    articles = json.load(f)
                    all_articles.extend(articles)
            except (json.JSONDecodeError, IOError):
                continue

        if not all_articles:
            continue

        # Verdict distribution
        verdicts = {}
        for r in all_articles:
            v = r.get("raw_verdict_text", "").strip() or "EMPTY"
            verdicts[v] = verdicts.get(v, 0) + 1

        # Date range — only ISO dates for stats
        # Raw BS strings are not counted here
        dates = sorted([
            r.get("date_published", "")[:10]
            for r in all_articles
            if r.get("date_published", "")
            and r.get("date_published", "")[0].isdigit()
            and len(r.get("date_published", "")) >= 10
        ])

        stats["by_source"][source_name] = {
            "total": len(all_articles),
            "verdict_distribution": verdicts,
            "oldest_article": dates[0] if dates else "",
            "newest_article": dates[-1] if dates else "",
            "empty_verdicts": verdicts.get("EMPTY", 0),
        }

        stats["total_raw_articles"] += len(all_articles)

    return stats


def save_raw_stats(stats: dict, run_id: str) -> None:
    """Save raw stats to raw/stats_raw.json."""
    stats_file = RAW_DIR / "stats_raw.json"
    stats["last_updated"] = datetime.now(timezone.utc).isoformat()
    stats["run_id"] = run_id

    with open(stats_file, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


# =============================================================================
# COLLECTOR
# =============================================================================

def run_collector() -> None:
    """
    Main entry point for Stage 1 pipeline.
    Runs all active scrapers incrementally and updates state.
    """
    run_id = datetime.now().strftime("run_%Y%m%d_%H%M%S")

    create_directories()
    logger = setup_logging(run_id)
    logger.info(f"Starting collector — run_id: {run_id}")
    logger.info(f"Active sources: {list(ACTIVE_SOURCES.keys())}")

    last_run = load_last_run()
    logger.info(f"Last run: {last_run.get('last_run_date', 'never')}")

    # Track results per source
    run_results = {}

    for source_name in ACTIVE_SOURCES:
        logger.info(f"{'='*50}")
        logger.info(f"Running scraper: {source_name}")

        try:
            scraper = _get_scraper(source_name)
            if scraper is None:
                logger.error(f"No scraper found for: {source_name}")
                run_results[source_name] = {
                    "status": "failed",
                    "error": "scraper not found",
                    "articles_scraped": 0,
                    "last_published_date": last_run.get(
                        "sources", {}
                    ).get(source_name, {}).get("last_published_date"),
                }
                continue

            # Run scraper
            articles = scraper.run()

            # Get max published_date_iso from scraped articles
            # This becomes the new cutoff for next run
            max_published = scraper.get_max_published_date(articles)

            # Keep previous last_published_date if no new articles
            prev_published = last_run.get(
                "sources", {}
            ).get(source_name, {}).get("last_published_date")

            new_published = max_published or prev_published

            run_results[source_name] = {
                "status": "success",
                "articles_scraped": len(articles),
                "last_run_date": datetime.now().strftime("%Y-%m-%d"),
                "last_published_date": new_published,
            }

            logger.info(
                f"{source_name} complete — "
                f"{len(articles)} new articles | "
                f"last_published_date: {new_published}"
            )

        except Exception as e:
            logger.error(f"{source_name} failed: {e}")
            # Preserve previous last_published_date on failure
            prev_published = last_run.get(
                "sources", {}
            ).get(source_name, {}).get("last_published_date")

            run_results[source_name] = {
                "status": "failed",
                "error": str(e),
                "articles_scraped": 0,
                "last_published_date": prev_published,
            }

    # Save last_run.json
    last_run_state = {
        "last_run_date": datetime.now().strftime("%Y-%m-%d"),
        "run_id": run_id,
        "sources": run_results,
    }
    save_last_run(last_run_state)
    logger.info("Updated last_run.json")

    # Compute and save raw stats
    stats = compute_raw_stats()
    save_raw_stats(stats, run_id)
    logger.info(f"Updated stats_raw.json")
    logger.info(f"Total raw articles: {stats['total_raw_articles']}")

    # -------------------------------------------------------------------------
    # STAGE 2 — Normalize and export
    # -------------------------------------------------------------------------
    logger.info("Starting Stage 2 — normalization and export")
    try:
        from pipeline.normalizer import normalize_all
        from pipeline.deduplicator import deduplicate, get_dedup_stats
        from pipeline.exporter import export

        examples = normalize_all()

        deduped = deduplicate(examples)
        dedup_stats = get_dedup_stats(examples, deduped)
        logger.info(
            f"Dedup: {dedup_stats['removed']} removed, "
            f"{dedup_stats['after']} kept "
            f"({dedup_stats['removal_rate']} removal rate)"
        )

        dataset_stats = export(deduped)
        logger.info(
            f"Stage 2 complete — "
            f"{dataset_stats.get('total_examples', 0)} examples exported"
        )
    except Exception as e:
        logger.error(f"Stage 2 failed: {e}")

    # Summary
    logger.info(f"{'='*50}")
    logger.info(f"Collector complete — run_id: {run_id}")
    for source, result in run_results.items():
        status = result['status']
        count = result.get('articles_scraped', 0)
        last_pub = result.get('last_published_date', 'unknown')
        logger.info(
            f"  {source}: {status} — "
            f"{count} articles | "
            f"last_published: {last_pub}"
        )


def _get_scraper(source_name: str):
    """Dynamically import and return scraper instance for active sources."""
    try:
        if source_name == "techpana":
            from scrapers.techpana import TechpanaScraper
            return TechpanaScraper()

        elif source_name == "nepalfactcheck":
            from scrapers.nepalfactcheck import NepalfactcheckScraper
            return NepalfactcheckScraper()

        else:
            return None

    except Exception as e:
        logging.getLogger("nepfakev2.collector").error(
            f"Failed to import scraper for {source_name}: {e}"
        )
        return None


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    run_collector()