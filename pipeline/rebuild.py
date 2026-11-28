# pipeline/rebuild.py
# =============================================================================
# Rebuild data/ from the committed raw/ files, OFFLINE.
# Stage 2 only: normalize -> dedup -> claim groups + splits -> export ->
# README stats. No scraping, no Hugging Face push.
#
# The weekly collector calls build_dataset() too, so the weekly data and a
# local rebuild are made by the same code.
#
# The first rebuild that replaces a pre-2.0 CSV also writes
# data/id_map_v1_to_v2.csv (old example_id -> new example_id, by URL).
#
# Usage:
#   python -m pipeline.rebuild
# =============================================================================

import logging
import re
from pathlib import Path

import pandas as pd

from config.settings import DATA_DIR

ID_MAP_FILE = "id_map_v1_to_v2.csv"
V1_ID = re.compile(r"^NF2_\d{8}_\d{4}$")


def write_id_map(old_csv: Path, examples, out_dir: Path) -> int:
    """Map pre-2.0 IDs to 2.0 IDs through source_url. Returns rows written
    (0 when the old CSV has no v1 IDs, so the map is written only once)."""
    from utils.helpers import canonical_url
    if not Path(old_csv).exists():
        return 0
    old = pd.read_csv(old_csv, usecols=["example_id", "source_url"], dtype=str)
    old = old[old["example_id"].str.match(V1_ID.pattern)]
    if old.empty:
        return 0
    new = {canonical_url(e.source_url): e.example_id for e in examples}
    m = pd.DataFrame({
        "old_example_id": old["example_id"],
        "new_example_id": [new.get(canonical_url(u), "") for u in old["source_url"]],
        "source_url": old["source_url"],
    }).drop_duplicates("old_example_id")
    m.to_csv(Path(out_dir) / ID_MAP_FILE, index=False, encoding="utf-8",
             lineterminator="\n")
    return len(m)


def build_dataset(out_dir=None, fixed_timestamp: str = None, update_readme: bool = True) -> dict:
    """normalize -> dedup -> splits -> export. Returns the stats dict."""
    from pipeline import deduplicator, normalizer
    from pipeline.exporter import export
    from pipeline.splitter import assign_splits

    out = Path(out_dir) if out_dir else DATA_DIR
    examples = normalizer.normalize_all()
    deduped = deduplicator.deduplicate(examples)
    assign_splits(deduped)

    mapped = write_id_map(out / "nepfakev2.csv", deduped, out)
    stats = export(deduped, normalizer.LAST_EXCLUSIONS, out_dir=out,
                   fixed_timestamp=fixed_timestamp)
    stats["_build"] = {
        "normalized": len(examples),
        "after_dedup": len(deduped),
        "replaced_snapshots": deduplicator.LAST_REPORT.get("replaced", 0),
        "label_changed": len(deduplicator.LAST_REPORT.get("label_changed", [])),
        "id_map_rows": mapped,
    }
    if update_readme and out_dir is None:
        from pipeline.update_readme import update_readme_stats
        stats["_build"]["readme_updated"] = update_readme_stats()
        from pipeline.versioning import sync_card_configs
        try:
            sync_card_configs()      # HF card configs follow data/vX.Y/
        except RuntimeError as e:    # old card without markers: the HF push refuses later
            logging.getLogger("nepfakev2.rebuild").warning(f"card configs not synced: {e}")
    return stats


def main() -> None:
    logging.basicConfig(level=logging.ERROR)
    stats = build_dataset()
    b = stats["_build"]
    print(f"normalized: {b['normalized']}  after dedup: {b['after_dedup']}  "
          f"exported: {stats.get('total_examples', 0)}  "
          f"schema: {stats.get('schema_version')}")
    print(f"excluded: {stats.get('excluded')}")
    print(f"newer snapshots replaced older ones: {b['replaced_snapshots']} "
          f"(label changed: {b['label_changed']})")
    print(f"main benchmark: {stats.get('main_benchmark')}")
    print(f"claim_source: {stats.get('claim_source_distribution')}")
    print(f"split (time): {stats.get('split_distribution')}  "
          f"split_random: {stats.get('split_random_distribution')}")
    if b["id_map_rows"]:
        print(f"wrote data/{ID_MAP_FILE} ({b['id_map_rows']} old IDs)")
    print("label_source:")
    for source, v in stats.get("label_source_distribution", {}).items():
        print(f"  {source:<17} {v['count']:>4}  {v['pct']}")
    print("README stats updated" if b.get("readme_updated") else "README stats NOT updated (markers?)")


if __name__ == "__main__":
    main()
