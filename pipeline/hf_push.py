# pipeline/hf_push.py
# =============================================================================
# Pushes NepFakeV2 dataset to Hugging Face after every pipeline run.
# Uploads: data/nepfakev2.csv, data/nepfakev2.json, data/stats.json
#
# Requires:
#   HF_TOKEN environment variable — Hugging Face write token
#   pip install huggingface_hub
#
# Usage:
#   from pipeline.hf_push import push_to_huggingface
#   Called automatically by collector.py after export.
# =============================================================================

import logging
import os
from pathlib import Path

from config.settings import DATA_DIR, BASE_DIR

logger = logging.getLogger("nepfakev2.hf_push")

HF_REPO_ID  = "Nandan007/NepFakeV2"
HF_REPO_TYPE = "dataset"

# Files to upload — path in HF repo : local path
UPLOAD_FILES = {
    "data/nepfakev2.csv":  DATA_DIR / "nepfakev2.csv",
    "data/nepfakev2.json": DATA_DIR / "nepfakev2.json",
    "data/stats.json":     DATA_DIR / "stats.json",
    "README.md":           BASE_DIR / "README_HF.md",  # HF dataset card
}


def push_to_huggingface() -> bool:
    """
    Push dataset files to Hugging Face Hub.

    Returns:
        True if upload succeeded, False if skipped or failed.
    """
    token = os.environ.get("HF_TOKEN")
    if not token:
        logger.warning(
            "HF_TOKEN not set — skipping Hugging Face push. "
            "Add HF_TOKEN to GitHub Actions secrets."
        )
        return False

    try:
        from huggingface_hub import HfApi
    except ImportError:
        logger.error(
            "huggingface_hub not installed — "
            "add it to requirements.txt and re-run."
        )
        return False

    api = HfApi(token=token)

    # Ensure repo exists — creates it if not
    try:
        api.create_repo(
            repo_id=HF_REPO_ID,
            repo_type=HF_REPO_TYPE,
            exist_ok=True,
            private=False,
        )
        logger.info(f"HF repo ready: {HF_REPO_ID}")
    except Exception as e:
        logger.error(f"Failed to ensure HF repo exists: {e}")
        return False

    # Upload each file
    failed = []
    for repo_path, local_path in UPLOAD_FILES.items():
        local_path = Path(local_path)
        if not local_path.exists():
            logger.warning(f"Skipping {repo_path} — file not found: {local_path}")
            continue

        try:
            api.upload_file(
                path_or_fileobj=str(local_path),
                path_in_repo=repo_path,
                repo_id=HF_REPO_ID,
                repo_type=HF_REPO_TYPE,
                commit_message=f"auto-update: {repo_path}",
            )
            logger.info(f"Uploaded: {repo_path}")
        except Exception as e:
            logger.error(f"Failed to upload {repo_path}: {e}")
            failed.append(repo_path)

    if failed:
        logger.error(f"HF push incomplete — failed files: {failed}")
        return False

    logger.info(f"HF push complete — {HF_REPO_ID}")
    return True