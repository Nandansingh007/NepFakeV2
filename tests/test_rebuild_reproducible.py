"""
Test plan N10: the committed data/ is exactly what the code makes from raw/.

Rebuilds into a temporary folder and compares bytes. Fails when someone
changes code without rebuilding, or edits data/ by hand.
"""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.data


def test_rebuild_reproduces_committed_files(tmp_path):
    from pipeline.rebuild import build_dataset
    stats = json.loads(Path("data/stats.json").read_text(encoding="utf-8"))
    build_dataset(out_dir=tmp_path, fixed_timestamp=stats["last_updated"], update_readme=False)
    for name in ("nepfakev2.csv", "nepfakev2.json", "excluded.csv", "stats.json"):
        new = (tmp_path / name).read_bytes()
        old = Path("data", name).read_bytes()
        assert new == old, f"data/{name} is not what the code builds from raw/: run python -m pipeline.rebuild"
