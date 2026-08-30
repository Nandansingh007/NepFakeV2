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
    "nepalcheck":     RAW_DIR / "nepalcheck",
    "nepalfactcheck": RAW_DIR / "nepalfactcheck",
    "bbc_nepali":     RAW_DIR / "bbc_nepali",
    "kantipur":       RAW_DIR / "kantipur",
}

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

SCHEMA_VERSION = "1.0"

# NepFakeV2 label definitions
LABELS = {
    0: "REAL",
    1: "FALSE_MISLEADING",
    2: "UNVERIFIED",
}

LABEL_TO_INT = {v: k for k, v in LABELS.items()}

# =============================================================================
# SCRAPING SETTINGS
# =============================================================================

# User agent — identify ourselves politely
USER_AGENT = (
    "NepFakeV2-Research-Bot/1.0 "
    "(Academic research; github.com/Nandansingh007/NepFakeV2; "
    "contact: nandansingh007@gmail.com)"
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