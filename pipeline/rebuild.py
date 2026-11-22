# pipeline/rebuild.py
# =============================================================================
# Rebuild data/ from the committed raw/ files, OFFLINE.
# Runs Stage 2 only (normalize -> dedup -> export -> README stats).
# No scraping, no Hugging Face push.
#
# Use after changing normalizer / label / schema code, then commit data/
# together with the code change.
#
# Usage:
#   python -m pipeline.rebuild
# =============================================================================

import logging


def main() -> None:
    logging.basicConfig(level=logging.ERROR)

    from pipeline.normalizer import normalize_all
    from pipeline.deduplicator import deduplicate
    from pipeline.exporter import export
    from pipeline.update_readme import update_readme_stats

    examples = normalize_all()
    deduped = deduplicate(examples)
    stats = export(deduped)
    readme_ok = update_readme_stats()

    print(f"normalized: {len(examples)}  after dedup: {len(deduped)}  "
          f"exported: {stats.get('total_examples', 0)}  "
          f"schema: {stats.get('schema_version')}")
    print("label_source:")
    for source, v in stats.get("label_source_distribution", {}).items():
        print(f"  {source:<17} {v['count']:>4}  {v['pct']}")
    print("README stats updated" if readme_ok else "README stats NOT updated (markers?)")


if __name__ == "__main__":
    main()
