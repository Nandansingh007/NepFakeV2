"""
The data contract (DATASHEET "Data contract"), one test per layer:

  raw        faithful copy of each fetch, never edited afterwards
  normalized every row passes the written rules; weaker rows are flagged
  excluded   every article left out, with a reason
  benchmark  a subset by a written rule; every other row says why not
  count      unique articles in raw = normalized + excluded, nothing lost
"""
import json
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from utils.helpers import canonical_url, snapshot_files

pytestmark = pytest.mark.data

EXCLUSION_REASONS = {"explainer", "not_a_factcheck", "verdict_unmappable",
                     "no_title_or_body", "hand_checked_not_factcheck", "validation_failed"}
SOURCES = ["techpana", "nepalfactcheck"]


def _raw_articles():
    keys = set()
    for s in SOURCES:
        for f, _ in snapshot_files(Path("raw", s)):   # live + raw/archive/
            for r in json.loads(f.read_text(encoding="utf-8")):
                keys.add((s, canonical_url(r["source_url"])))
    return keys


def _keys(df):
    return [(r.source_name, canonical_url(r.source_url)) for r in df.itertuples()]


@pytest.fixture(scope="module")
def layers():
    d = pd.read_csv("data/nepfakev2.csv", keep_default_na=False)
    x = pd.read_csv("data/excluded.csv", keep_default_na=False)
    return d, x


def test_count_raw_equals_normalized_plus_excluded(layers):
    d, x = layers
    raw = _raw_articles()
    norm, excl = _keys(d), _keys(x)
    assert len(norm) == len(set(norm)), "an article appears twice in the dataset"
    assert len(excl) == len(set(excl)), "an article appears twice in excluded.csv"
    assert not set(norm) & set(excl), "an article is both kept and excluded"
    lost = raw - set(norm) - set(excl)
    assert not lost, f"{len(lost)} raw articles are neither kept nor excluded: {sorted(lost)[:5]}"
    assert set(norm) | set(excl) <= raw, "a row does not come from raw"
    assert len(raw) == len(d) + len(x)
    stats = json.loads(Path("data/stats.json").read_text(encoding="utf-8"))
    assert stats["total_including_unknown"] == len(raw)


def test_every_excluded_article_has_a_known_reason(layers):
    _, x = layers
    bad = x[~x["reason"].isin(EXCLUSION_REASONS)]
    assert bad.empty, bad[["source_url", "reason"]].head().to_dict("records")


def test_every_row_outside_the_benchmark_says_why(layers):
    d, _ = layers
    inside = d["in_main_benchmark"].astype(str) == "True"
    assert (d.loc[inside, "benchmark_exclusion_reason"] == "").all()
    assert (d.loc[~inside, "benchmark_exclusion_reason"] != "").all()


def test_benchmark_reasons_follow_the_written_rule(layers):
    from pipeline.normalizer import benchmark_reasons
    d, _ = layers
    for r in d.itertuples():
        expected = benchmark_reasons(r.label_fine, r.label_source, r.language)
        # page_cut comes from raw (page_complete) and is not repeated here
        got = "|".join(p for p in r.benchmark_exclusion_reason.split("|") if p and p != "page_cut")
        assert got == expected, (r.source_url, got, expected)


def test_weaker_rows_are_flagged(layers):
    d, _ = layers
    gold = d["verified"] == "gold"
    assert (d.loc[gold, "label_source"] == "hand_checked").all()
    assert (d.loc[~gold, "verified"] == "silver").all()
    conflict = d["snapshot_conflict"].astype(str) == "True"
    assert (d.loc[conflict, "snapshot_other_label"] != "").all()
    assert (d.loc[~conflict, "snapshot_other_label"] == "").all()


def _archived_unchanged(path: str) -> bool:
    """raw/<source>/<f>.json was moved to raw/archive/<source>/<f>.json with
    the same content as the committed file. Compared as git sees it (git
    hash-object applies the same line-ending rules as git status), so a
    Windows checkout with core.autocrlf, where the files on disk have CRLF,
    is not reported as an edit."""
    p = Path(path)
    if p.parts[:1] != ("raw",) or "archive" in p.parts:
        return False
    archived = Path("raw", "archive", *p.parts[1:])
    if not archived.exists():
        return False
    git = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True,
                                    check=True).stdout.strip()
    try:
        return git("hash-object", archived.as_posix()) == git("rev-parse", f"HEAD:{p.as_posix()}")
    except subprocess.CalledProcessError:
        return False


def test_raw_files_are_never_edited():
    # Older raw files may only be added, never changed. Today's file may grow
    # (a second run on the same day). A live file may disappear only by being
    # moved, byte for byte, to raw/archive/<source>/ (pipeline/archive.py).
    # Skips outside a git checkout.
    try:
        out = subprocess.run(["git", "status", "--porcelain", "--", "raw"],
                             capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    today = date.today().isoformat()
    edited = []
    for line in out.splitlines():
        status, path = line[:2], line[3:].strip()
        name = Path(path).stem
        if ("M" in status or "D" in status) and path.endswith(".json") \
                and name[:4].isdigit() and name < today:
            if status.strip() == "D" and _archived_unchanged(path):
                continue
            edited.append(line)
    assert not edited, f"raw files edited or deleted: {edited}"
