# pipeline/splitter.py
# =============================================================================
# Splits (brief S3/S4): a time split and a random control split, both by
# claim group, frozen once in a file with a checksum.
#
#   split         time split by date_published (boundaries in
#                 config/settings.py SPLIT_TIME_BOUNDARIES). A claim group
#                 takes the split of its EARLIEST row, so a claim never sits
#                 in two splits.
#   split_random  control split: each claim group goes to train/dev/test by a
#                 hash of its ID (SPLIT_SEED, SPLIT_RANDOM_SHARES). Report it
#                 next to the time split: the FALSE/MISLEADING balance moves
#                 a lot between years, and a time split alone mostly measures
#                 that shift.
#
# Before the freeze both columns are PROVISIONAL and recomputed every build.
# Freezing (run once, after the Phase 2 full re-scrape):
#
#     python -m pipeline.splitter freeze
#
# writes data/splits_v2.0.csv (example_id, source_url, claim_group_id, split,
# split_random) and data/splits_v2.0.manifest.json (sha256 of the split
# file, counts, boundaries, date). After that, every build reads the file:
# rows in it keep their split forever; rows added later get "new" in both
# columns. The tests check the checksum, so an edited split file fails CI.
#
#     python -m pipeline.splitter check     # verify the checksum
#     python -m pipeline.splitter release   # data/v2.0/ release files (once)
#
# The release (brief section 6) is for people who will not read the code:
#   data/v2.0/train.csv dev.csv test.csv   main benchmark rows of each time split
#   data/v2.0/random_train.csv ...         the same rows by split_random
#   data/v2.0/nepfakev2_v2.0.jsonl         every row, all columns
#   data/v2.0/RELEASE.json                 version, date, counts, split checksum
#   data/v2.0/SHA256SUMS                   checksums of the files above
# =============================================================================

import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (SPLIT_FILE, SPLIT_MANIFEST, SPLIT_RANDOM_SHARES,
                             SPLIT_SEED, SPLIT_TIME_BOUNDARIES, SCHEMA_VERSION)
from pipeline.claim_groups import find_groups

SPLIT_COLUMNS = ["example_id", "source_url", "claim_group_id", "split", "split_random"]


def time_split(date_published: str) -> str:
    if not date_published or date_published <= SPLIT_TIME_BOUNDARIES["train_until"]:
        return "train"          # undated rows (none today) go to train
    if date_published <= SPLIT_TIME_BOUNDARIES["dev_until"]:
        return "dev"
    return "test"


def random_split(claim_group_id: str) -> str:
    h = hashlib.sha256(f"{SPLIT_SEED}:{claim_group_id}".encode("utf-8")).hexdigest()
    x = int(h[:8], 16) / 0x100000000
    edge = 0.0
    for name in ("train", "dev", "test"):
        edge += SPLIT_RANDOM_SHARES[name]
        if x < edge:
            return name
    return "test"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_frozen(split_file: Path = None, manifest: Path = None) -> dict:
    """{example_id: row} from the frozen file; {} before the freeze.
    Raises if the file does not match the manifest checksum."""
    split_file = Path(split_file or SPLIT_FILE)
    manifest = Path(manifest or SPLIT_MANIFEST)
    if not split_file.exists():
        return {}
    if not manifest.exists():
        raise RuntimeError(f"{split_file} exists but {manifest} is missing")
    expected = json.loads(manifest.read_text(encoding="utf-8"))["sha256"]
    if sha256_file(split_file) != expected:
        raise RuntimeError(f"{split_file} does not match the checksum in {manifest}; "
                           f"a frozen split must not be edited")
    with open(split_file, encoding="utf-8", newline="") as f:
        return {r["example_id"]: r for r in csv.DictReader(f)}


def assign_splits(examples, frozen: dict = None) -> None:
    """Set claim_group_id, split and split_random on every example (in place)."""
    frozen = load_frozen() if frozen is None else frozen
    groups = find_groups(examples)

    if frozen:
        # A new row about a claim that is already in a frozen group gets that
        # group's ID (so it is visible as a repeat), but split "new": rows
        # after the freeze are never part of the frozen benchmark.
        frozen_gid = {}
        for e in examples:
            row = frozen.get(e.example_id)
            if row:
                frozen_gid.setdefault(groups[e.example_id], row["claim_group_id"])
        for e in examples:
            row = frozen.get(e.example_id)
            if row:
                e.claim_group_id, e.split, e.split_random = (
                    row["claim_group_id"], row["split"], row["split_random"])
            else:
                gid = groups[e.example_id]
                e.claim_group_id = frozen_gid.get(gid, gid)
                e.split, e.split_random = "new", "new"
        return

    earliest = {}
    for e in examples:
        gid = groups[e.example_id]
        d = e.date_published or ""
        if gid not in earliest or (d and (not earliest[gid] or d < earliest[gid])):
            earliest[gid] = d
    for e in examples:
        gid = groups[e.example_id]
        e.claim_group_id = gid
        e.split = time_split(earliest[gid])
        e.split_random = random_split(gid)


def freeze(examples, split_file: Path = None, manifest: Path = None) -> dict:
    """Write the split file and its manifest. Refuses to overwrite."""
    split_file = Path(split_file or SPLIT_FILE)
    manifest = Path(manifest or SPLIT_MANIFEST)
    if split_file.exists():
        raise RuntimeError(f"{split_file} already exists: splits are frozen. "
                           f"A new freeze needs a new release (new file name).")
    assign_splits(examples, frozen={})
    rows = sorted(({"example_id": e.example_id, "source_url": e.source_url,
                    "claim_group_id": e.claim_group_id, "split": e.split,
                    "split_random": e.split_random} for e in examples),
                  key=lambda r: r["example_id"])
    split_file.parent.mkdir(parents=True, exist_ok=True)
    with open(split_file, "w", encoding="utf-8", newline="\n") as f:
        w = csv.DictWriter(f, fieldnames=SPLIT_COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    def counts(col):
        out = {}
        for e in examples:
            if e.in_main_benchmark:
                k = getattr(e, col)
                out.setdefault(k, {"FALSE": 0, "MISLEADING": 0})[e.label_fine] += 1
        return out

    info = {
        "schema_version": SCHEMA_VERSION,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "rows": len(rows),
        "claim_groups": len({r["claim_group_id"] for r in rows}),
        "sha256": sha256_file(split_file),
        "time_boundaries": SPLIT_TIME_BOUNDARIES,
        "random_shares": SPLIT_RANDOM_SHARES,
        "random_seed": SPLIT_SEED,
        "main_benchmark_by_split": counts("split"),
        "main_benchmark_by_split_random": counts("split_random"),
    }
    with open(manifest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    return info


def release(csv_path: Path = None, out_dir: Path = None, citation: Path = None) -> dict:
    """Write the release files (data/v2.0/) from data/nepfakev2.csv, once.

    Only after the freeze (provisional splits must not be released), and
    never over an earlier release: release files are immutable, a fix goes
    into the next version (VERSIONING.md). Only frozen rows are released;
    rows added after the freeze ("new") are not part of the benchmark.
    """
    import pandas as pd
    from config.settings import (DATA_DIR, DATASET_VERSION, RELEASE_DIR,
                                 RELEASE_TAG, BASE_DIR)
    csv_path = Path(csv_path or DATA_DIR / "nepfakev2.csv")
    if citation is None and out_dir is None:     # the real release, not a test
        citation = BASE_DIR / "CITATION.cff"
    out_dir = Path(out_dir or RELEASE_DIR)
    frozen = load_frozen(SPLIT_FILE, SPLIT_MANIFEST)   # also checks the checksum
    if not frozen:
        raise RuntimeError("splits are not frozen: run `python -m pipeline.splitter freeze` first")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"{out_dir} already exists: {RELEASE_TAG} is released and must "
                           f"not change. A fix goes into the next version (VERSIONING.md).")
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    df = df[df["example_id"].isin(frozen.keys())]
    out_dir.mkdir(parents=True, exist_ok=True)
    bench = df[df["in_main_benchmark"] == "True"]
    written = {}
    for col, prefix in (("split", ""), ("split_random", "random_")):
        for name in ("train", "dev", "test"):
            part = bench[bench[col] == name]
            path = out_dir / f"{prefix}{name}.csv"
            part.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
            written[path.name] = len(part)
    jsonl = out_dir / f"nepfakev2_v{DATASET_VERSION}.jsonl"
    with open(jsonl, "w", encoding="utf-8", newline="\n") as f:
        for rec in df.to_dict(orient="records"):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    written[jsonl.name] = len(df)
    dates = sorted(d for d in df["date_published"] if d)
    info = {
        "release": RELEASE_TAG,
        "schema_version": SCHEMA_VERSION,
        "released_at": datetime.now(timezone.utc).date().isoformat(),
        "rows": len(df),
        "main_benchmark_rows": len(bench),
        "date_range": [dates[0], dates[-1]] if dates else [],
        "split_file_sha256": sha256_file(Path(SPLIT_FILE)),
        "files": dict(sorted(written.items())),
        "official_metric": "macro-F1 over FALSE and MISLEADING on test.csv "
                           "(time split); also report random_test.csv",
    }
    (out_dir / "RELEASE.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8", newline="\n")
    names = sorted(written) + ["RELEASE.json"]
    sums = "".join(f"{sha256_file(out_dir / n)}  {n}\n" for n in names)
    (out_dir / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")
    if citation:
        _set_citation_date(Path(citation), DATASET_VERSION, info["released_at"])
    return written


def _set_citation_date(path: Path, version: str, day: str) -> None:
    """CITATION.cff names the release and its date (not the code date)."""
    import re
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version: .*$', f'version: "{version}"', text)
    text = re.sub(r'(?m)^date-released: .*$', f'date-released: "{day}"', text)
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "check":
        frozen = load_frozen()
        print(f"OK: {len(frozen)} frozen rows, checksum matches" if frozen
              else "not frozen yet (provisional splits)")
        return 0
    if cmd == "freeze":
        import logging
        logging.basicConfig(level=logging.ERROR)
        from pipeline.normalizer import normalize_all
        from pipeline.deduplicator import deduplicate
        info = freeze(deduplicate(normalize_all()))
        print(json.dumps(info, ensure_ascii=False, indent=2))
        print("Now run: python -m pipeline.rebuild  (writes the frozen splits into data/)")
        return 0
    if cmd == "release":
        from config.settings import RELEASE_TAG
        for name, n in release().items():
            print(f"  {name:<28} {n:>5} rows")
        from pipeline.versioning import sync_card_configs
        sync_card_configs()
        print(f"Card configs updated (README_HF.md now has benchmark-{RELEASE_TAG}).")
        print("Next: commit and push, run the workflow, then tag (VERSIONING.md).")
        return 0
    print("usage: python -m pipeline.splitter freeze | check | release")
    return 2


if __name__ == "__main__":
    sys.exit(main())
