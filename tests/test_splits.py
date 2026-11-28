"""
Test: claim groups and splits (v2.0, brief S3/S4).

- Two articles about the same claim share claim_group_id, and a claim group
  never sits in two splits (time or random).
- Each split has enough of both classes to measure anything.
- The frozen split file cannot be edited without failing (checksum), rows
  added after the freeze get "new", and freezing twice is refused.
"""
import json

import pytest

KNOWN_PAIRS = [
    # Wagle statue (both 10 Sep 2026)
    ("https://techpana.com/2026/159019/swornim-wagle-statue-viral-image-ai-generated-fact-check",
     "https://nepalfactcheck.org/2026/09/swarnim-wagle-statue-ai-generated-image-fact-check/"),
    # Mahesh Basnet in Dhangadhi (7 and 8 Feb 2026)
    ("https://techpana.com/2026/155277/fact-check-misleading-two-month-old-video-viral-claiming-mahesh-basnet-beaten-in-dhangadhi",
     "https://nepalfactcheck.org/2026/02/no-evidence-mahesh-basnet-was-assaulted-in-dhangadhi/"),
]


@pytest.fixture(scope="module")
def split_rows(deduped):
    from pipeline.splitter import assign_splits
    assign_splits(deduped)
    return deduped


@pytest.mark.data
@pytest.mark.parametrize("a, b", KNOWN_PAIRS)
def test_known_pairs_share_a_group(split_rows, a, b):
    by = {e.source_url: e for e in split_rows}
    assert by[a].claim_group_id == by[b].claim_group_id


@pytest.mark.data
def test_no_group_in_two_splits(split_rows):
    for col in ("split", "split_random"):
        seen = {}
        bad = []
        for e in split_rows:
            s = getattr(e, col)
            if s == "new":
                continue    # added after the freeze: outside the benchmark
            if seen.setdefault(e.claim_group_id, s) != s:
                bad.append(e.claim_group_id)
        assert not bad, (col, bad[:5])


@pytest.mark.data
def test_no_near_duplicate_evidence_across_splits(split_rows):
    # Independent of the grouping rule: the same opening 200 characters of
    # evidence in two different splits means a copy slipped through.
    first = {}
    bad = []
    for e in split_rows:
        key = e.evidence_text[:200]
        if len(key) < 200 or e.split == "new":
            continue
        if key in first and first[key] != e.split:
            bad.append(e.source_url)
        first.setdefault(key, e.split)
    assert not bad, bad[:5]


@pytest.mark.data
def test_no_near_duplicate_claims_across_splits(split_rows):
    # Test plan B1, independent of the grouping rule: character 4-gram
    # Jaccard of two claims in different splits must stay below 0.8 unless
    # they share a group.
    def grams(t):
        t = " ".join(t.split())
        return {t[i:i + 4] for i in range(max(len(t) - 3, 0))}
    rows = [(e, grams(e.claim_text)) for e in split_rows if e.split != "new"]
    index = {}
    for i, (_, g) in enumerate(rows):
        for x in g:
            index.setdefault(x, []).append(i)
    bad = []
    for i, (a, ga) in enumerate(rows):
        counts = {}
        for x in ga:
            for j in index[x]:
                if j > i:
                    counts[j] = counts.get(j, 0) + 1
        for j, shared in counts.items():
            b, gb = rows[j]
            if a.split != b.split and a.claim_group_id != b.claim_group_id:
                if shared / max(len(ga) + len(gb) - shared, 1) >= 0.8:
                    bad.append((a.source_url, b.source_url))
    assert not bad, bad[:5]


@pytest.mark.data
def test_label_prior_shift_is_reported(split_rows):
    # Not a failure: the FALSE share moves a lot between years. The warning
    # keeps it visible in every CI log (state it in the paper).
    import warnings
    def share(name):
        rows = [e for e in split_rows if e.in_main_benchmark and e.split == name]
        return sum(e.label_fine == "FALSE" for e in rows) / max(len(rows), 1)
    gap = abs(share("train") - share("test"))
    if gap > 0.15:
        warnings.warn(f"FALSE share train {share('train'):.0%} vs test {share('test'):.0%}: "
                      f"report split_random next to the time split")


@pytest.mark.data
def test_every_split_has_both_classes(split_rows):
    from collections import Counter
    for col in ("split", "split_random"):
        c = Counter((getattr(e, col), e.label_fine) for e in split_rows if e.in_main_benchmark)
        for split in ("train", "dev", "test"):
            for label in ("FALSE", "MISLEADING"):
                assert c[(split, label)] >= 25, (col, split, label, c[(split, label)])


@pytest.mark.data
def test_time_split_follows_dates(split_rows):
    from config.settings import SPLIT_TIME_BOUNDARIES as B
    groups = {}
    for e in split_rows:
        if e.split != "new":
            groups.setdefault(e.claim_group_id, []).append(e)
    for rows in groups.values():
        first = min(e.date_published for e in rows)
        want = "train" if first <= B["train_until"] else "dev" if first <= B["dev_until"] else "test"
        assert {e.split for e in rows} == {want}


def test_random_split_is_deterministic():
    from pipeline.splitter import random_split
    assert random_split("G_tp_159019") == random_split("G_tp_159019")
    from collections import Counter
    c = Counter(random_split(f"G_{i}") for i in range(5000))
    assert 0.66 < c["train"] / 5000 < 0.74 and 0.17 < c["test"] / 5000 < 0.23


def _mini(n=40):
    from schema.schema import NepFakeV2Example
    rows = []
    for i in range(n):
        rows.append(NepFakeV2Example(
            example_id=f"NF2_tp_{1000 + i}", claim_text=f"दाबी नम्बर {i} विषय{i} ठाउँ{i}",
            verdict_label=1, verdict_label_text="FALSE_MISLEADING",
            evidence_text="प्रमाण", source_name="techpana",
            source_url=f"https://techpana.com/2026/{1000 + i}/x",
            date_published=f"202{4 + i % 3}-03-01", label_fine="FALSE"))
    return rows


def test_freeze_writes_checksum_and_refuses_twice(tmp_path):
    from pipeline import splitter
    f, m = tmp_path / "splits.csv", tmp_path / "manifest.json"
    info = splitter.freeze(_mini(), f, m)
    assert info["rows"] == 40 and info["sha256"] == splitter.sha256_file(f)
    assert len(splitter.load_frozen(f, m)) == 40
    with pytest.raises(RuntimeError):
        splitter.freeze(_mini(), f, m)


def test_edited_split_file_fails_checksum(tmp_path):
    from pipeline import splitter
    f, m = tmp_path / "splits.csv", tmp_path / "manifest.json"
    splitter.freeze(_mini(), f, m)
    f.write_text(f.read_text(encoding="utf-8").replace(",train,", ",test,", 1), encoding="utf-8")
    with pytest.raises(RuntimeError, match="checksum"):
        splitter.load_frozen(f, m)


def test_rows_after_the_freeze_are_new(tmp_path):
    from pipeline import splitter
    f, m = tmp_path / "splits.csv", tmp_path / "manifest.json"
    rows = _mini()
    rows[0].claim_text = "काठमाडौँ महानगरले बागमती किनारमा बनाएको पुल भत्किएको भिडिओ धरहरा नजिक"
    splitter.freeze(rows[:30], f, m)
    frozen = splitter.load_frozen(f, m)
    again = _mini()
    splitter.assign_splits(again, frozen=frozen)
    assert {e.split for e in again[30:]} == {"new"}
    assert {e.split_random for e in again[30:]} == {"new"}
    # a new row about a frozen claim keeps the frozen group's ID
    from pipeline.splitter import assign_splits
    twin = _mini()[:31]
    same = "काठमाडौँ महानगरले बागमती किनारमा बनाएको पुल भत्किएको भिडिओ धरहरा नजिक"
    twin[0].claim_text = twin[30].claim_text = same
    twin[30].date_published = twin[0].date_published
    assign_splits(twin, frozen=frozen)
    assert twin[30].claim_group_id == twin[0].claim_group_id and twin[30].split == "new"
    before = {r["example_id"]: r["split"] for r in frozen.values()}
    assert all(e.split == before[e.example_id] for e in again[:30])


@pytest.mark.data
def test_committed_split_file_matches_manifest():
    from config.settings import SPLIT_FILE, SPLIT_MANIFEST
    from pipeline import splitter
    if not SPLIT_FILE.exists():
        pytest.skip("splits not frozen yet (run after the Phase 2 re-scrape)")
    info = json.loads(SPLIT_MANIFEST.read_text(encoding="utf-8"))
    assert splitter.sha256_file(SPLIT_FILE) == info["sha256"]


@pytest.mark.data
def test_committed_csv_uses_the_frozen_splits():
    import pandas as pd
    from config.settings import SPLIT_FILE
    if not SPLIT_FILE.exists():
        pytest.skip("splits not frozen yet")
    from pipeline.splitter import load_frozen
    frozen = load_frozen()
    df = pd.read_csv("data/nepfakev2.csv", dtype=str)
    for _, r in df.iterrows():
        if r["example_id"] in frozen:
            assert r["split"] == frozen[r["example_id"]]["split"]
        else:
            assert r["split"] == "new"


def _csv(tmp_path, rows):
    import pandas as pd
    from schema.schema import to_dict
    path = tmp_path / "nepfakev2.csv"
    pd.DataFrame([to_dict(r) for r in rows]).to_csv(path, index=False)
    return path


def test_release_refuses_provisional_splits(tmp_path, monkeypatch):
    from pipeline import splitter
    monkeypatch.setattr(splitter, "SPLIT_FILE", tmp_path / "none.csv")
    rows = _mini()
    splitter.assign_splits(rows, frozen={})
    with pytest.raises(RuntimeError, match="not frozen"):
        splitter.release(_csv(tmp_path, rows), tmp_path / "out")


def test_release_writes_split_files_and_checksums(tmp_path, monkeypatch):
    from pipeline import splitter
    f, m = tmp_path / "splits.csv", tmp_path / "manifest.json"
    rows = _mini()
    for r in rows:
        r.in_main_benchmark = True
    splitter.freeze(rows, f, m)
    monkeypatch.setattr(splitter, "SPLIT_FILE", f)
    monkeypatch.setattr(splitter, "SPLIT_MANIFEST", m)
    written = splitter.release(_csv(tmp_path, rows), tmp_path / "out")
    assert sum(written[n] for n in ("train.csv", "dev.csv", "test.csv")) == 40
    sums = (tmp_path / "out" / "SHA256SUMS").read_text(encoding="utf-8")
    assert "train.csv" in sums and "nepfakev2_v2.0.jsonl" in sums and "RELEASE.json" in sums
