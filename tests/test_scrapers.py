"""
Test: scraper imports, initialization and pure helper functions.
Nothing here fetches a page (network is blocked in pytest.ini).
"""
import pytest


def test_scrapers_import():
    from scrapers.base import BaseScraper  # noqa: F401
    from scrapers.techpana import TechpanaScraper  # noqa: F401
    from scrapers.nepalfactcheck import NepalfactcheckScraper  # noqa: F401


# TechpanaScraper.__init__ tries to open a FlareSolverr session on
# localhost:8191. In tests that call is blocked by pytest-socket and the
# scraper swallows the error, so construction still succeeds.
@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_techpana_init():
    from scrapers.techpana import TechpanaScraper
    s = TechpanaScraper()
    assert s.source_name == "techpana"
    assert s.config is not None
    assert s.raw_dir is not None


def test_nepalfactcheck_init():
    from scrapers.nepalfactcheck import NepalfactcheckScraper
    s = NepalfactcheckScraper()
    assert s.source_name == "nepalfactcheck"
    assert s.config is not None


@pytest.mark.parametrize(
    "raw, expected",
    [("भदौ ९, २०८३", "2026-08-25"), ("साउन २८, २०८३", "2026-08-13"), ("", None)],
)
def test_parse_bs_date(raw, expected):
    from scrapers.techpana import parse_bs_date
    assert parse_bs_date(raw) == expected


@pytest.mark.parametrize(
    "filename, expected",
    [
        ("false_image.jpg", "मिथ्या"),
        ("misleading_photo.jpg", "भ्रामक"),
        ("verified_true.jpg", "सही"),
        ("", None),
    ],
)
def test_extract_verdict_from_image(filename, expected):
    from scrapers.techpana import extract_verdict_from_image
    assert extract_verdict_from_image(filename) == expected


def test_normalize_url_strips_query():
    from utils.helpers import normalize_url
    assert normalize_url("https://techpana.com/2026/158464/slug?tab=nepali") == \
        "https://techpana.com/2026/158464/slug"


def test_url_hash_stable_across_query_params():
    from utils.helpers import url_hash
    assert url_hash("https://techpana.com/2026/158464/slug?tab=nepali") == \
        url_hash("https://techpana.com/2026/158464/slug")


def test_title_hash_stable_across_whitespace():
    from utils.helpers import title_hash
    assert title_hash("भाइरल भिडिओ भ्रामक") == title_hash("भाइरल भिडिओ भ्रामक  ")


def test_is_devanagari():
    # is_devanagari() lives in config.settings, not utils.helpers
    from config.settings import is_devanagari
    assert is_devanagari("भाइरल") is True
    assert is_devanagari("hello") is False
