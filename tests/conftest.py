"""
Shared pytest setup for NepFakeV2.

- Every test runs with the repo root as the working directory, because the
  code and some tests use relative paths like raw/ and data/.
- The expensive pipeline steps (normalize_all, deduplicate) run once per
  test session and are shared via fixtures, instead of once per file.
"""
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _run_from_repo_root(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def normalized():
    """Output of normalize_all() on the committed raw/ files."""
    os.chdir(REPO_ROOT)
    from pipeline.normalizer import normalize_all
    return normalize_all()


@pytest.fixture(scope="session")
def deduped(normalized):
    from pipeline.deduplicator import deduplicate
    return deduplicate(normalized)
