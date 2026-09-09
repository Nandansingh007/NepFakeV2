"""
Test: scraper imports and initialization
Verifies all scrapers can be imported and initialized correctly.
"""
import sys
sys.path.insert(0, '.')

errors = []

# --- Test imports ---
try:
    from scrapers.base import BaseScraper
    from scrapers.techpana import TechpanaScraper
    from scrapers.nepalfactcheck import NepalfactcheckScraper
except ImportError as e:
    errors.append(f"Import error: {e}")

# --- Test initialization ---
try:
    s = TechpanaScraper()
    assert s.source_name == "techpana"
    assert s.config is not None
    assert s.raw_dir is not None
except Exception as e:
    errors.append(f"TechpanaScraper init error: {e}")

try:
    s = NepalfactcheckScraper()
    assert s.source_name == "nepalfactcheck"
    assert s.config is not None
except Exception as e:
    errors.append(f"NepalfactcheckScraper init error: {e}")

# --- Test helper functions ---
try:
    from scrapers.techpana import parse_bs_date, BS_MONTHS

    result = parse_bs_date("भदौ ९, २०८३")
    assert result == "2026-08-25", f"Expected 2026-08-25, got {result}"

    result = parse_bs_date("साउन २८, २०८३")
    assert result == "2026-08-13", f"Expected 2026-08-13, got {result}"

    result = parse_bs_date("")
    assert result is None

except Exception as e:
    errors.append(f"BS date conversion error: {e}")

# --- Test verdict extraction ---
try:
    from scrapers.techpana import extract_verdict_from_image, extract_verdict_from_body

    assert extract_verdict_from_image("false_image.jpg") == "मिथ्या"
    assert extract_verdict_from_image("misleading_photo.jpg") == "भ्रामक"
    assert extract_verdict_from_image("verified_true.jpg") == "सही"
    assert extract_verdict_from_image("") is None

except Exception as e:
    errors.append(f"Verdict extraction error: {e}")

# --- Test utils ---
# Note: is_devanagari() lives in config.settings — not utils.helpers
try:
    from utils.helpers import normalize_url, url_hash, title_hash
    from config.settings import is_devanagari

    # normalize_url
    assert normalize_url("https://techpana.com/2026/158464/slug?tab=nepali") == \
           "https://techpana.com/2026/158464/slug"

    # url_hash stability across query params
    h1 = url_hash("https://techpana.com/2026/158464/slug?tab=nepali")
    h2 = url_hash("https://techpana.com/2026/158464/slug")
    assert h1 == h2, "url_hash not stable across query params"

    # title_hash stability across whitespace
    h1 = title_hash("भाइरल भिडिओ भ्रामक")
    h2 = title_hash("भाइरल भिडिओ भ्रामक  ")
    assert h1 == h2, "title_hash not stable across whitespace"

    # is_devanagari
    assert is_devanagari("भाइरल") == True
    assert is_devanagari("hello") == False

except Exception as e:
    errors.append(f"Utils error: {e}")

if errors:
    print("FAIL — scraper errors:")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print("PASS — scrapers: all imports, initialization and helpers working")