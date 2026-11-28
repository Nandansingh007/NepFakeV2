"""
Test: the Hugging Face push sends every file in ONE commit (no network:
huggingface_hub is replaced by a fake).
"""
import sys
import types

import pytest


def test_required_files_exist_after_build():
    from pipeline.hf_push import files_to_upload
    files = files_to_upload()
    assert {"data/nepfakev2.csv", "data/stats.json", "data/excluded.csv", "README.md"} <= set(files)


def test_push_is_one_commit(monkeypatch):
    calls = {}

    class Op:
        def __init__(self, path_in_repo, path_or_fileobj):
            self.path_in_repo = path_in_repo

    class Api:
        def __init__(self, token):
            pass

        def create_repo(self, **kw):
            pass

        def create_commit(self, operations, **kw):
            calls["paths"] = [o.path_in_repo for o in operations]

        def upload_file(self, **kw):
            raise AssertionError("upload_file must not be used (not atomic)")

    fake = types.SimpleNamespace(HfApi=Api, CommitOperationAdd=Op)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    monkeypatch.setenv("HF_TOKEN", "x")
    from pipeline.hf_push import push_to_huggingface
    assert push_to_huggingface() is True
    assert "data/nepfakev2.csv" in calls["paths"] and "README.md" in calls["paths"]


def test_push_aborts_when_a_required_file_is_missing(monkeypatch, tmp_path):
    from pipeline import hf_push
    monkeypatch.setitem(hf_push.REQUIRED_FILES, "data/excluded.csv", tmp_path / "missing.csv")
    with pytest.raises(FileNotFoundError):
        hf_push.files_to_upload()


def test_card_docs_are_uploaded():
    # The card links to these; before 28 Nov 2026 the Hub copies were never refreshed
    from pipeline.hf_push import files_to_upload
    assert {"DATASHEET.md", "VERSIONING.md", "CITATION.cff"} <= set(files_to_upload())

