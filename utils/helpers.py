# utils/helpers.py
# =============================================================================
# Shared utility functions for NepFakeV2 pipeline.
# Used by collector.py for incremental tracking only.
# Deduplication utilities used in Stage 2 cleaning.
#
# Note: is_devanagari() is defined in config.settings — import from there.
# =============================================================================

import hashlib
from pathlib import Path
from urllib.parse import urlparse, urlunparse


def normalize_url(url: str) -> str:
    """
    Normalize a URL by stripping query parameters and fragments.
    Used to identify same article accessed via different URLs.

    Examples:
        techpana.com/2026/158464/slug?tab=nepali → techpana.com/2026/158464/slug
        techpana.com/2026/158464/slug#section    → techpana.com/2026/158464/slug
        techpana.com/2026/158464/slug            → techpana.com/2026/158464/slug

    Args:
        url: Raw URL string

    Returns:
        Normalized URL string
    """
    try:
        parsed = urlparse(url)
        return urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return url


def canonical_url(url: str) -> str:
    """
    One spelling per article, used for identity (example_id) and dedup.
    Stronger than normalize_url(): also drops "www.", lower-cases the host,
    ignores http vs https and a trailing slash.

        http://www.NepalFactCheck.org/2026/09/x/?a=1#top
        -> https://nepalfactcheck.org/2026/09/x
    """
    try:
        parsed = urlparse((url or "").strip())
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = parsed.path.rstrip("/")
        return urlunparse(("https", host, path, "", "", ""))
    except Exception:
        return url


def archive_dir_for(raw_dir) -> Path:
    """raw/<source>/ -> raw/archive/<source>/ (older snapshots, moved there
    unchanged after a full re-scrape; see pipeline/archive.py)."""
    raw_dir = Path(raw_dir)
    return raw_dir.parent / "archive" / raw_dir.name


def snapshot_files(raw_dir) -> list:
    """Every raw JSON file of one source, archive and live, oldest first
    (file name = scrape date; on the same date the archived file comes
    first). [(path, "archive" | "live"), ...]"""
    raw_dir = Path(raw_dir)
    files = [(f, "archive") for f in sorted(archive_dir_for(raw_dir).glob("*.json"))]
    files += [(f, "live") for f in sorted(raw_dir.glob("*.json"))] if raw_dir.exists() else []
    return sorted(files, key=lambda x: (x[0].stem, x[1] != "archive"))


def url_hash(url: str) -> str:
    """
    Generate a stable 16-char hash from a normalized URL.
    Used as incremental tracking ID in last_run.json.
    Same article always produces same hash regardless of
    query params or fragments.

    Args:
        url: Raw URL string

    Returns:
        16-character hex string e.g. "a3f8c2d1e9b47f6a"
    """
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def title_hash(title: str) -> str:
    """
    Generate a stable 12-char hash from a normalized title.
    Used in Stage 2 deduplication to detect same article
    published under different URLs.

    Normalization: lowercase + collapse whitespace

    Args:
        title: Article headline string

    Returns:
        12-character hex string e.g. "a3f8c2d1e9b4"
    """
    clean = " ".join(title.strip().lower().split())
    return hashlib.md5(clean.encode("utf-8")).hexdigest()[:12]