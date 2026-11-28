# config/settings.py
# =============================================================================
# Central configuration for NepFakeV2.
# All paths, logging, and global settings defined here.
# No other file should hardcode paths or settings.
# Usage:
#   from config.settings import SOURCES, RAW_DIR, DATA_DIR
# =============================================================================

import yaml
import logging
from pathlib import Path
from datetime import datetime

# =============================================================================
# BASE PATHS
# =============================================================================

BASE_DIR  = Path(__file__).parent.parent   # NepFakeV2/
CONFIG_DIR = BASE_DIR / "config"
RAW_DIR   = BASE_DIR / "raw"
DATA_DIR  = BASE_DIR / "data"
LOGS_DIR  = BASE_DIR / "logs"
SCHEMA_DIR = BASE_DIR / "schema"

# Raw subdirectories — one per source
RAW_DIRS = {
    "techpana":       RAW_DIR / "techpana",
    "nepalfactcheck": RAW_DIR / "nepalfactcheck",
}

# Older snapshots: after a full re-scrape the earlier raw files of a source
# are moved here unchanged (pipeline/archive.py), so raw/<source>/ holds the
# latest full scrape plus the weekly runs after it. The pipeline still reads
# the archive: an archived copy is used only when no live copy of that
# article is usable (snapshot_source = "archive").
ARCHIVE_DIR = RAW_DIR / "archive"
ARCHIVE_MANIFEST = ARCHIVE_DIR / "MANIFEST.csv"

# State file — tracks last run date per source
LAST_RUN_FILE = RAW_DIR / "last_run.json"

# Dataset output files
DATASET_CSV  = DATA_DIR / "nepfakev2.csv"
DATASET_JSON = DATA_DIR / "nepfakev2.json"
STATS_FILE   = DATA_DIR / "stats.json"

# =============================================================================
# CREATE DIRECTORIES IF THEY DON'T EXIST
# =============================================================================

def create_directories():
    """Create all required directories if they don't exist."""
    dirs = [
        RAW_DIR,
        DATA_DIR,
        LOGS_DIR,
        *RAW_DIRS.values(),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

# =============================================================================
# LOAD SOURCES CONFIG
# =============================================================================

def load_sources():
    """Load and return sources configuration from sources.yaml."""
    config_path = CONFIG_DIR / "sources.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config["sources"]

SOURCES = load_sources()

# Active sources only
ACTIVE_SOURCES = {
    name: config
    for name, config in SOURCES.items()
    if config.get("active", False)
}

# =============================================================================
# SCHEMA
# =============================================================================

SCHEMA_VERSION = "2.0"   # 1.1: label_source; 2.0: see CHANGELOG.md (labels, IDs, clean text, splits)

# NepFakeV2 label definitions
# -1 = UNKNOWN: verdict present in source but no mapping defined
LABELS = {
    0:  "REAL",
    1:  "FALSE_MISLEADING",
    2:  "UNVERIFIED",
    -1: "UNKNOWN",
}

LABEL_TO_INT = {v: k for k, v in LABELS.items()}

# Fine labels (schema 2.0). verdict_label above is the coarse label and is
# kept unchanged; label_fine splits FALSE_MISLEADING into FALSE / MISLEADING.
LABELS_FINE = {
    "FALSE":      "मिथ्या: the claim is fabricated or untrue",
    "MISLEADING": "भ्रामक: real content, wrong context or a distorted claim",
    "TRUE":       "सही: the claim is accurate",
    "UNVERIFIED": "अपुष्ट: could not be confirmed or refuted",
}
# There is no MIXED label (removed 28 Nov 2026). A TechPana conclusion that
# names both मिथ्या and भ्रामक takes the verdict of its claim sentence
# (label_source conclusion_claim); if that also names both, MISLEADING
# (label_source conclusion_mixed). See scrapers/techpana.py resolve_verdict.

# Every fine label has exactly one coarse label
LABEL_FINE_TO_COARSE = {
    "FALSE": 1, "MISLEADING": 1,
    "TRUE": 0,
    "UNVERIFIED": 2,
}

# Main benchmark task: FALSE vs MISLEADING. Rows whose verdict was not read
# from the article text are left out (in_main_benchmark = False):
#   stored            only the scraper's badge (decision 22 Nov 2026:
#                     excluded until hand-checked)
# conclusion_mixed rows (MISLEADING by rule, 28 Nov 2026) are in the
# benchmark; filter on label_source to drop them.
BENCHMARK_EXCLUDED_SOURCES = {"stored"}

# NepalFactCheck's summary box ("दावी : … / दावीकर्ता : … / तथ्य : …") is the
# fact-checker's own one-line answer. False (default since 28 Nov 2026): it
# goes to conclusion_text, like TechPana's निष्कर्ष box, and evidence_text is
# the article's reasoning only. True: it stays at the end of evidence_text
# (the behaviour before 28 Nov 2026).
NFC_BOX_IN_EVIDENCE = False

# Where a record's verdict was read (label_source column, schema 1.1).
# Set in pipeline/normalizer.py; TechPana rule in scrapers/techpana.py
# resolve_verdict().
LABEL_SOURCES = {
    "nfc_header":       "NepalFactCheck header tag (line 3 of the body)",
    "conclusion":       "TechPana conclusion box names exactly one verdict",
    "conclusion_claim": "TechPana conclusion names both मिथ्या and भ्रामक; the "
                        "sentence about the claim (दाबी) names one, and that one is used",
    "conclusion_mixed": "TechPana conclusion and its claim sentence name both "
                        "मिथ्या and भ्रामक (or there is no claim sentence): MISLEADING",
    "summary":          "TechPana lead summary (no usable conclusion)",
    "stored":           "value the scraper stored: TechPana og:image badge "
                        "(files before 12 Oct 2026 may hold a sidebar badge), "
                        "NepalFactCheck article without a header tag",
    "hand_checked":     "a person read the article (data_validation/reference_labels.csv)",
}

# Where claim_text came from (pipeline/claim_extractor.py)
#   claim_box          NFC summary box "दावी : …"
#   headline_question  NFC headline "के … हो?"
#   claim_caption      TechPana: the post's text quoted in the "दाबी" section
#   lead_quote / lead / claim_section / headline   fallbacks, both outlets
#   hand_checked       a person wrote or confirmed it
#                      (data_validation/claims_reference.csv)
CLAIM_SOURCES = ("claim_box", "headline_question", "claim_caption",
                 "lead_quote", "lead", "claim_section", "headline", "hand_checked")

# =============================================================================
# SPLITS (pipeline/splitter.py)
# =============================================================================
# Time split: by date_published. The boundaries are a decision (see
# DATASHEET.md); changing them after the freeze needs a new release.
SPLIT_TIME_BOUNDARIES = {
    "train_until": "2024-12-31",   # train: <= this date
    "dev_until":   "2025-12-31",   # dev:   2025
}                                   # test:  after dev_until
# Random control split (split_random): by claim group, so one claim never
# sits in two splits. Shares of claim groups, seeded by a hash.
SPLIT_RANDOM_SHARES = {"train": 0.70, "dev": 0.10, "test": 0.20}
SPLIT_SEED = "nepfakev2-2.0"
# Claim groups: two articles about the same claim (often TechPana and
# NepalFactCheck checking the same viral post) share claim_group_id.
CLAIM_GROUP_MAX_DAYS = 30
CLAIM_GROUP_MIN_SIMILARITY = 0.35      # share of the smaller claim's word weight
CLAIM_GROUP_MIN_SHARED_WEIGHT = 12.0   # about 3 rare words in common
# Frozen split file: written once by `python -m pipeline.splitter freeze`
SPLIT_FILE = BASE_DIR / "data" / "splits_v2.0.csv"
SPLIT_MANIFEST = BASE_DIR / "data" / "splits_v2.0.manifest.json"

# =============================================================================
# VERSIONS AND TAGS (VERSIONING.md)
# =============================================================================
# DATASET_VERSION names the benchmark release (git tag and HF tag "v2.0").
# It is not SCHEMA_VERSION: v2.1 can add frozen rows on schema 2.0.
DATASET_VERSION = "2.0"
RELEASE_TAG = f"v{DATASET_VERSION}"
# Release files, written once by `python -m pipeline.splitter release`
RELEASE_DIR = BASE_DIR / "data" / RELEASE_TAG
# Every successful weekly push is tagged "run-YYYY-MM-DD" (UTC date) on
# GitHub and on Hugging Face. A run tag is a data snapshot, not a benchmark.
RUN_TAG_PREFIX = "run-"

# =============================================================================
# SCRAPING SETTINGS
# =============================================================================

# User agent — identify ourselves politely
USER_AGENT = (
    "NepFakeV2-Research-Bot/1.0 "
    "(Academic research; github.com/Nandansingh007/NepFakeV2; "
    "contact: nandan.singhs007@gmail.com)"
)

# Default request timeout in seconds
REQUEST_TIMEOUT = 30

# =============================================================================
# LOGGING
# =============================================================================

def setup_logging(run_id: str = None) -> logging.Logger:
    """
    Set up logging for a pipeline run.
    Logs to both console and a dated log file in logs/.
    
    Args:
        run_id: Optional run identifier. Defaults to current timestamp.
    
    Returns:
        Configured logger instance.
    """
    if run_id is None:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Ensure logs directory exists
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_file = LOGS_DIR / f"{run_id}_scrape.log"

    # Log format
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-8s %(name)-20s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Root logger
    logger = logging.getLogger("nepfakev2")
    logger.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # File handler — DEBUG and above (full detail)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Avoid duplicate handlers if called multiple times
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    logger.info(f"Logging initialized — run_id: {run_id}")
    logger.info(f"Log file: {log_file}")

    return logger


# =============================================================================
# DEVANAGARI DETECTION
# =============================================================================

def is_devanagari(text: str) -> bool:
    """
    Returns True if text contains Devanagari Unicode characters.
    Devanagari range: U+0900 to U+097F
    
    Args:
        text: Input string to check.
    
    Returns:
        True if Devanagari characters found, False otherwise.
    """
    return any("\u0900" <= char <= "\u097F" for char in text)