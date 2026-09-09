# utils/helpers.py
# =============================================================================
# Shared utility functions for NepFakeV2 pipeline.
# Used by collector.py for incremental tracking only.
# Deduplication utilities used in Stage 2 cleaning.
#
# Note: is_devanagari() is defined in config.settings — import from there.
# =============================================================================

import hashlib
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