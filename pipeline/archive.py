"""
Move older raw snapshots to raw/archive/<source>/ after a full re-scrape.

raw/<source>/ then holds the latest full scrape and the weekly runs after it;
raw/archive/<source>/ holds every earlier file, byte for byte. Nothing is
edited or deleted (data contract: raw is a faithful copy of each fetch).
Each move is recorded in raw/archive/MANIFEST.csv with the file's sha256.

The pipeline still reads the archive (utils/helpers.py snapshot_files): an
archived copy is used only when no live copy of that article is usable,
and such rows say snapshot_source = "archive".
"""
import csv
import hashlib
import logging
import os
from datetime import date
from pathlib import Path

from config.settings import ARCHIVE_MANIFEST, RAW_DIRS
from utils.helpers import archive_dir_for

logger = logging.getLogger("nepfakev2.archive")

MANIFEST_COLUMNS = ["source_name", "file", "sha256", "archived_on", "full_rescrape_file"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def archive_older(source_name: str, keep_stem: str, raw_dir=None,
                  manifest: Path = None, today: str = None) -> list:
    """Move every raw/<source>/*.json except <keep_stem>.json (the full
    re-scrape's own file) into raw/archive/<source>/. Returns the moved
    file names. Never overwrites: a file already in the archive with the
    same bytes is only removed from live; different bytes raise."""
    raw_dir = Path(raw_dir or RAW_DIRS[source_name])
    manifest = Path(manifest or ARCHIVE_MANIFEST)
    dest_dir = archive_dir_for(raw_dir)
    moved, rows = [], []
    for f in sorted(raw_dir.glob("*.json")):
        if f.stem >= keep_stem:          # the full scrape's file and anything newer stay
            continue
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.name
        digest = sha256(f)
        if dest.exists():
            if sha256(dest) != digest:
                raise RuntimeError(f"{dest} already archived with different content")
            f.unlink()
        else:
            os.replace(f, dest)
        moved.append(f.name)
        rows.append({"source_name": source_name, "file": f"{source_name}/{f.name}",
                     "sha256": digest, "archived_on": today or date.today().isoformat(),
                     "full_rescrape_file": f"{keep_stem}.json"})
    if rows:
        new_file = not manifest.exists()
        manifest.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest, "a", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
            if new_file:
                w.writeheader()
            w.writerows(rows)
        logger.info(f"{source_name}: {len(moved)} older raw files moved to {dest_dir}")
    return moved


if __name__ == "__main__":
    import sys
    # python -m pipeline.archive 2026-11-28  (archive everything older than that file)
    keep = sys.argv[1]
    for s in RAW_DIRS:
        print(s, archive_older(s, keep))
