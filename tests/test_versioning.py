"""
Versions and tags (VERSIONING.md): run tags, release folder, card configs,
Hub tagging checks and the official scorer. No network: huggingface_hub is
replaced by a fake where needed.
"""
import sys
import types
import tempfile
from datetime import datetime, timezone
from pathlib import Path


import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


# --- names -------------------------------------------------------------------

def test_run_tag_is_utc_date():
    from pipeline.versioning import run_tag, RUN_TAG_RE
    tag = run_tag(datetime(2026, 11, 30, 0, 20, tzinfo=timezone.utc))
    assert tag == "run-2026-11-30" and RUN_TAG_RE.match(tag)


def test_release_name_is_separate_from_schema():
    from config.settings import DATASET_VERSION, RELEASE_TAG, RELEASE_DIR, SCHEMA_VERSION
    assert RELEASE_TAG == f"v{DATASET_VERSION}"
    assert RELEASE_DIR.name == RELEASE_TAG
    assert SCHEMA_VERSION == "2.0"


# --- card configs ------------------------------------------------------------

def _front_matter(text):
    return yaml.safe_load(text.split("---")[1])


def test_committed_card_is_valid_yaml_with_live_default():
    meta = _front_matter((ROOT / "README_HF.md").read_text(encoding="utf-8"))
    names = [c["config_name"] for c in meta["configs"]]
    assert names[0] == "default" and meta["configs"][0].get("default") is True
    for key in ("license", "language", "task_categories", "task_ids",
                "annotations_creators", "language_creators", "size_categories", "pretty_name"):
        assert meta.get(key), key


def test_card_has_no_release_config_before_the_release():
    # The card must never point at files that do not exist on the Hub.
    from pipeline.versioning import release_dirs
    meta = _front_matter((ROOT / "README_HF.md").read_text(encoding="utf-8"))
    released = {d.name for d in release_dirs()}
    for c in meta["configs"][1:]:
        assert any(c["config_name"].startswith(f"benchmark-{t}") for t in released), c
        for f in c["data_files"]:
            assert (ROOT / f["path"]).exists(), f["path"]


def test_sync_adds_configs_only_when_release_folder_exists(tmp_path):
    from pipeline.versioning import sync_card_configs
    card = tmp_path / "card.md"
    card.write_text((ROOT / "README_HF.md").read_text(encoding="utf-8"), encoding="utf-8")
    data = tmp_path / "data"
    data.mkdir()
    sync_card_configs(card, data)
    assert [c["config_name"] for c in _front_matter(card.read_text(encoding="utf-8"))["configs"]] == ["default"]

    rel = data / "v2.0"
    rel.mkdir()
    (rel / "train.csv").write_text("x\n", encoding="utf-8")
    sync_card_configs(card, data)                      # no SHA256SUMS yet: not a release
    assert len(_front_matter(card.read_text(encoding="utf-8"))["configs"]) == 1

    (rel / "SHA256SUMS").write_text("", encoding="utf-8")
    assert sync_card_configs(card, data) is True
    meta = _front_matter(card.read_text(encoding="utf-8"))
    names = [c["config_name"] for c in meta["configs"]]
    assert names == ["default", "benchmark-v2.0", "benchmark-v2.0-random"]
    bench = meta["configs"][1]["data_files"]
    assert [(f["split"], f["path"]) for f in bench] == [
        ("train", "data/v2.0/train.csv"), ("validation", "data/v2.0/dev.csv"),
        ("test", "data/v2.0/test.csv")]
    assert sync_card_configs(card, data) is False      # idempotent


# --- release folder ------------------------------------------------------------

def _frozen_release(tmp_path, monkeypatch):
    from pipeline import splitter
    from tests.test_splits import _mini, _csv
    f, m = tmp_path / "splits.csv", tmp_path / "manifest.json"
    rows = _mini()
    for r in rows:
        r.in_main_benchmark = True
    splitter.freeze(rows, f, m)
    monkeypatch.setattr(splitter, "SPLIT_FILE", f)
    monkeypatch.setattr(splitter, "SPLIT_MANIFEST", m)
    return splitter, _csv(tmp_path, rows)


def test_release_is_written_once(tmp_path, monkeypatch):
    splitter, csv_path = _frozen_release(tmp_path, monkeypatch)
    out = tmp_path / "v2.0"
    splitter.release(csv_path, out)
    with pytest.raises(RuntimeError, match="already exists"):
        splitter.release(csv_path, out)


def test_release_json_and_checksums_agree(tmp_path, monkeypatch):
    import json
    splitter, csv_path = _frozen_release(tmp_path, monkeypatch)
    out = tmp_path / "v2.0"
    written = splitter.release(csv_path, out)
    info = json.loads((out / "RELEASE.json").read_text(encoding="utf-8"))
    assert info["release"] == "v2.0" and info["rows"] == 40
    assert info["files"] == dict(sorted(written.items()))
    for line in (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ")
        assert splitter.sha256_file(out / name) == digest


def test_release_leaves_rows_after_the_freeze_out(tmp_path, monkeypatch):
    import pandas as pd
    splitter, csv_path = _frozen_release(tmp_path, monkeypatch)
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    extra = df.iloc[[0]].copy()
    extra["example_id"], extra["split"], extra["split_random"] = "NF2_tp_9999", "new", "new"
    pd.concat([df, extra]).to_csv(csv_path, index=False)
    written = splitter.release(csv_path, tmp_path / "v2.0")
    assert written["nepfakev2_v2.0.jsonl"] == 40


def test_release_sets_citation_version_and_date(tmp_path, monkeypatch):
    splitter, csv_path = _frozen_release(tmp_path, monkeypatch)
    cff = tmp_path / "CITATION.cff"
    cff.write_text('title: "x"\nversion: "1.1"\ndate-released: "2026-01-01"   # note\n', encoding="utf-8")
    splitter.release(csv_path, tmp_path / "v2.0", citation=cff)
    text = cff.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).date().isoformat()
    assert 'version: "2.0"' in text and f'date-released: "{today}"' in text


def test_release_folder_is_uploaded(tmp_path, monkeypatch):
    from pipeline import hf_push
    rel = tmp_path / "v2.0"
    rel.mkdir()
    for n in ("train.csv", "SHA256SUMS"):
        (rel / n).write_text("x", encoding="utf-8")
    monkeypatch.setattr(hf_push, "DATA_DIR", tmp_path)
    files = hf_push.files_to_upload()
    assert {"data/v2.0/train.csv", "data/v2.0/SHA256SUMS"} <= set(files)


# --- Hub tags (fake huggingface_hub) -------------------------------------------

def _fake_hub(monkeypatch, remote_files, remote_sums="", tags=()):
    calls = []

    class Api:
        def __init__(self, token):
            pass

        def create_tag(self, **kw):
            calls.append(kw)

        def list_repo_files(self, **kw):
            return list(remote_files)

        def list_repo_refs(self, **kw):
            return types.SimpleNamespace(tags=[types.SimpleNamespace(name=t) for t in tags])

    def download(**kw):
        p = Path(kw.get("local_dir") or tempfile.gettempdir()) / "SHA256SUMS_remote"
        p.write_text(remote_sums, encoding="utf-8")
        return str(p)

    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        types.SimpleNamespace(HfApi=Api, hf_hub_download=download))
    monkeypatch.setenv("HF_TOKEN", "x")
    return calls


def test_hf_run_tag_keeps_an_existing_tag(monkeypatch):
    from pipeline.versioning import hf_tag
    calls = _fake_hub(monkeypatch, [])
    hf_tag("run-2026-11-30")
    assert calls[0]["tag"] == "run-2026-11-30" and calls[0]["exist_ok"] is True
    with pytest.raises(ValueError):
        hf_tag("v2.0")


def _local_release(tmp_path):
    rel = tmp_path / "v2.0"
    rel.mkdir()
    (rel / "test.csv").write_text("x", encoding="utf-8")
    (rel / "SHA256SUMS").write_text("abc  test.csv\n", encoding="utf-8")
    return rel


def test_hf_release_tag_refuses_when_hub_lacks_files(tmp_path, monkeypatch):
    from pipeline.versioning import hf_release_tag
    rel = _local_release(tmp_path)
    calls = _fake_hub(monkeypatch, ["data/nepfakev2.csv"])
    with pytest.raises(RuntimeError, match="does not have the release files"):
        hf_release_tag("v2.0", rel)
    assert not calls


def test_hf_release_tag_refuses_different_checksums(tmp_path, monkeypatch):
    from pipeline.versioning import hf_release_tag
    rel = _local_release(tmp_path)
    calls = _fake_hub(monkeypatch, ["data/v2.0/test.csv", "data/v2.0/SHA256SUMS"],
                      remote_sums="zzz  test.csv\n")
    with pytest.raises(RuntimeError, match="differs"):
        hf_release_tag("v2.0", rel)
    assert not calls


def test_hf_release_tag_is_never_moved(tmp_path, monkeypatch):
    from pipeline.versioning import hf_release_tag
    rel = _local_release(tmp_path)
    _fake_hub(monkeypatch, ["data/v2.0/test.csv", "data/v2.0/SHA256SUMS"],
              remote_sums="abc  test.csv\n", tags=["v2.0"])
    with pytest.raises(RuntimeError, match="never moved"):
        hf_release_tag("v2.0", rel)


def test_hf_release_tag_when_hub_matches(tmp_path, monkeypatch):
    from pipeline.versioning import hf_release_tag
    rel = _local_release(tmp_path)
    calls = _fake_hub(monkeypatch, ["data/v2.0/test.csv", "data/v2.0/SHA256SUMS"],
                      remote_sums="abc  test.csv\n")
    hf_release_tag("v2.0", rel)
    assert calls[0]["tag"] == "v2.0" and not calls[0].get("exist_ok")


# --- workflow --------------------------------------------------------------------

def test_workflow_tags_only_after_the_hub_push():
    wf = yaml.safe_load((ROOT / ".github/workflows/weekly_scrape.yml").read_text(encoding="utf-8"))
    assert wf["permissions"]["contents"] == "write"
    steps = [s["name"] for s in wf["jobs"]["scrape"]["steps"]]
    tests, commit = steps.index("Run tests on the freshly scraped data"), steps.index("Commit and push")
    push = steps.index("Push dataset to Hugging Face")
    tag = steps.index("Tag this run (run-YYYY-MM-DD)")
    assert tests < commit < push < tag
    step = wf["jobs"]["scrape"]["steps"][tag]
    assert "if" not in step                      # never runs after a failure
    assert "pipeline.versioning hf-tag" in step["run"] and "git push origin" in step["run"]


# --- scorer ----------------------------------------------------------------------

def test_scores_and_majority_baseline():
    from pipeline.evaluate import scores
    gold = {"a": "FALSE", "b": "MISLEADING", "c": "MISLEADING", "d": "MISLEADING"}
    perfect = scores(gold, dict(gold))
    assert perfect["macro_f1"] == 1.0 and perfect["accuracy"] == 1.0
    major = scores(gold, {k: "MISLEADING" for k in gold})
    assert major["macro_f1"] == pytest.approx(major["majority_macro_f1"])
    assert major["accuracy"] == pytest.approx(0.75)


def test_scorer_refuses_incomplete_or_unknown_predictions():
    from pipeline.evaluate import scores
    gold = {"a": "FALSE", "b": "MISLEADING"}
    with pytest.raises(ValueError, match="missing"):
        scores(gold, {"a": "FALSE"})
    with pytest.raises(ValueError, match="unknown"):
        scores(gold, {"a": "FALSE", "b": "TRUE"})


def test_scorer_refuses_before_the_release(tmp_path, capsys):
    from pipeline.evaluate import main
    pred = tmp_path / "p.csv"
    pred.write_text("example_id,prediction\n", encoding="utf-8")
    assert main([str(pred), "--release-dir", str(tmp_path / "v2.0")]) == 2
    assert "not released yet" in capsys.readouterr().out
