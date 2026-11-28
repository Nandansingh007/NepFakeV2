# pipeline/hf_push.py
# =============================================================================
# Pushes NepFakeV2 to Hugging Face after the weekly test gate passed.
#
# All files go up in ONE commit (create_commit). Before 2.0 each file was a
# separate upload, so a failure half-way left the Hub with a new CSV next to
# an old card and old stats (brief B-item: atomic push).
#
# Requires:
#   HF_TOKEN environment variable — Hugging Face write token
#   pip install huggingface_hub
# =============================================================================

import logging
import os
from pathlib import Path

from config.settings import BASE_DIR, DATA_DIR, SCHEMA_VERSION, SPLIT_FILE, SPLIT_MANIFEST

logger = logging.getLogger("nepfakev2.hf_push")

HF_REPO_ID = "Nandan007/NepFakeV2"
HF_REPO_TYPE = "dataset"

# path in the HF repo : local path. Required files must exist; optional ones
# (the frozen split files exist only after the freeze) are sent if present.
REQUIRED_FILES = {
    "data/nepfakev2.csv":  DATA_DIR / "nepfakev2.csv",
    "data/nepfakev2.json": DATA_DIR / "nepfakev2.json",
    "data/stats.json":     DATA_DIR / "stats.json",
    "data/excluded.csv":   DATA_DIR / "excluded.csv",
    "README.md":           BASE_DIR / "README_HF.md",   # dataset card
}
OPTIONAL_FILES = {
    "data/id_map_v1_to_v2.csv":         DATA_DIR / "id_map_v1_to_v2.csv",
    f"data/{Path(SPLIT_FILE).name}":     SPLIT_FILE,
    f"data/{Path(SPLIT_MANIFEST).name}": SPLIT_MANIFEST,
    "DATASHEET.md":                      BASE_DIR / "DATASHEET.md",
    "CITATION.cff":                      BASE_DIR / "CITATION.cff",
    "VERSIONING.md":                     BASE_DIR / "VERSIONING.md",
}
# Kept for older callers
UPLOAD_FILES = dict(REQUIRED_FILES)


def files_to_upload() -> dict:
    """{repo_path: local_path}; raises FileNotFoundError if a required file is missing."""
    missing = [str(p) for p in REQUIRED_FILES.values() if not Path(p).exists()]
    if missing:
        raise FileNotFoundError(f"required files missing: {missing}")
    out = dict(REQUIRED_FILES)
    out.update({k: v for k, v in OPTIONAL_FILES.items() if Path(v).exists()})
    # Release folders (data/v2.0/ ...), present only after `splitter release`.
    # They are re-sent unchanged every week; the card lists them as configs.
    from pipeline.versioning import release_dirs
    for d in release_dirs(DATA_DIR):
        for f in sorted(d.iterdir()):
            if f.is_file():
                out[f"data/{d.name}/{f.name}"] = f
    return out


def push_to_huggingface() -> bool:
    """One commit with every file. True on success, False if skipped/failed."""
    token = os.environ.get("HF_TOKEN")
    if not token:
        logger.warning("HF_TOKEN not set — skipping Hugging Face push.")
        return False
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
    except ImportError:
        logger.error("huggingface_hub not installed — add it to requirements.txt.")
        return False

    try:
        from pipeline.versioning import sync_card_configs
        sync_card_configs()          # card configs match the release folders
        files = files_to_upload()
    except (FileNotFoundError, RuntimeError) as e:
        logger.error(f"HF push aborted: {e}")
        return False

    api = HfApi(token=token)
    try:
        api.create_repo(repo_id=HF_REPO_ID, repo_type=HF_REPO_TYPE,
                        exist_ok=True, private=False)
        ops = [CommitOperationAdd(path_in_repo=repo_path, path_or_fileobj=str(local))
               for repo_path, local in sorted(files.items())]
        api.create_commit(
            repo_id=HF_REPO_ID, repo_type=HF_REPO_TYPE, operations=ops,
            commit_message=f"auto-update (schema {SCHEMA_VERSION}): {len(ops)} files")
    except Exception as e:
        logger.error(f"HF push failed, nothing changed on the Hub: {e}")
        return False

    logger.info(f"HF push complete — {HF_REPO_ID} ({len(files)} files, one commit)")
    return True
