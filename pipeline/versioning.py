# pipeline/versioning.py
# =============================================================================
# Tags and release configs (VERSIONING.md).
#
#   run-YYYY-MM-DD  every successful weekly push, on GitHub and on Hugging
#                   Face. A snapshot of the live data. Not a benchmark.
#   v2.0            the benchmark release: frozen splits plus data/v2.0/.
#                   Made once, by hand, after `splitter release`.
#
# The Hugging Face card (README_HF.md) gets one "benchmark-vX.Y" config per
# release folder that exists (data/vX.Y/ with SHA256SUMS). Before the freeze
# there is none, so the card never points at files that do not exist.
#
#   python -m pipeline.versioning run-tag-name      # prints today's run tag
#   python -m pipeline.versioning hf-tag run-2026-11-30
#   python -m pipeline.versioning release-tag       # HF tag v2.0, after checks
#   python -m pipeline.versioning sync-card         # rewrite the configs block
#
# Needs HF_TOKEN (a write token) for the two hf commands. Git tags are made
# with git itself (workflow step, or the commands in VERSIONING.md).
# =============================================================================

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from config.settings import BASE_DIR, DATA_DIR, RELEASE_DIR, RELEASE_TAG, RUN_TAG_PREFIX

CARD_PATH = BASE_DIR / "README_HF.md"
CONFIGS_START = "# RELEASE_CONFIGS_START"
CONFIGS_END = "# RELEASE_CONFIGS_END"
RUN_TAG_RE = re.compile(r"^run-\d{4}-\d{2}-\d{2}$")
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+$")


def run_tag(now: datetime = None) -> str:
    """Tag for a weekly run: run-YYYY-MM-DD, UTC date."""
    now = now or datetime.now(timezone.utc)
    return f"{RUN_TAG_PREFIX}{now.strftime('%Y-%m-%d')}"


def release_dirs(data_dir: Path = None) -> list:
    """Released versions present locally: data/vX.Y/ that hold SHA256SUMS."""
    data_dir = Path(data_dir or DATA_DIR)
    found = [p for p in data_dir.glob("v*") if p.is_dir()
             and RELEASE_TAG_RE.match(p.name) and (p / "SHA256SUMS").exists()]
    return sorted(found, key=lambda p: tuple(int(x) for x in p.name[1:].split(".")))


def configs_block(data_dir: Path = None) -> str:
    """YAML lines for the release configs (empty before the first release)."""
    lines = []
    for d in release_dirs(data_dir):
        tag = d.name
        for name, prefix in ((f"benchmark-{tag}", ""), (f"benchmark-{tag}-random", "random_")):
            lines.append(f"- config_name: {name}")
            lines.append("  data_files:")
            for split, stem in (("train", "train"), ("validation", "dev"), ("test", "test")):
                lines.append(f"  - split: {split}")
                lines.append(f"    path: data/{tag}/{prefix}{stem}.csv")
    return "\n".join(lines)


def sync_card_configs(card_path: Path = None, data_dir: Path = None) -> bool:
    """Rewrite the block between the markers. True if the card changed."""
    card_path = Path(card_path or CARD_PATH)
    if not card_path.exists():
        return False
    text = card_path.read_text(encoding="utf-8")
    start, end = text.find(CONFIGS_START), text.find(CONFIGS_END)
    if start == -1 or end == -1 or end < start:
        raise RuntimeError(f"{card_path}: release config markers missing")
    head = text[:text.index("\n", start) + 1]
    block = configs_block(data_dir)
    new = head + (block + "\n" if block else "") + text[end:]
    if new == text:
        return False
    card_path.write_text(new, encoding="utf-8", newline="\n")
    return True


def _api():
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise RuntimeError("HF_TOKEN is not set (a Hugging Face write token is needed)")
    from huggingface_hub import HfApi
    from pipeline.hf_push import HF_REPO_ID, HF_REPO_TYPE
    return HfApi(token=token), HF_REPO_ID, HF_REPO_TYPE


def hf_tag(tag: str) -> str:
    """Tag the current Hub main as a run tag. Keeps an existing tag."""
    if not RUN_TAG_RE.match(tag):
        raise ValueError(f"not a run tag: {tag!r} (expected run-YYYY-MM-DD)")
    api, repo, rtype = _api()
    api.create_tag(repo_id=repo, repo_type=rtype, tag=tag, exist_ok=True,
                   tag_message=f"Weekly data run {tag}")
    return tag


def hf_release_tag(tag: str = RELEASE_TAG, release_dir: Path = None) -> str:
    """Tag the Hub as the release, only if the Hub already holds exactly the
    local release files (same SHA256SUMS). Refuses to move an existing tag."""
    if not RELEASE_TAG_RE.match(tag):
        raise ValueError(f"not a release tag: {tag!r} (expected vX.Y)")
    release_dir = Path(release_dir or RELEASE_DIR)
    sums = release_dir / "SHA256SUMS"
    if not sums.exists():
        raise RuntimeError(f"{sums} missing: run `python -m pipeline.splitter release` first")
    api, repo, rtype = _api()
    remote = set(api.list_repo_files(repo_id=repo, repo_type=rtype))
    needed = {f"data/{tag}/{p.name}" for p in release_dir.iterdir() if p.is_file()}
    missing = sorted(needed - remote)
    if missing:
        raise RuntimeError(f"the Hub does not have the release files yet: {missing[:5]}. "
                           f"Push first (run the workflow), then tag.")
    from huggingface_hub import hf_hub_download
    remote_sums = Path(hf_hub_download(repo_id=repo, repo_type=rtype,
                                       filename=f"data/{tag}/SHA256SUMS",
                                       token=os.environ["HF_TOKEN"])).read_text(encoding="utf-8")
    if remote_sums != sums.read_text(encoding="utf-8"):
        raise RuntimeError("the Hub's SHA256SUMS differs from the local one: do not tag")
    refs = api.list_repo_refs(repo_id=repo, repo_type=rtype)
    if any(t.name == tag for t in getattr(refs, "tags", [])):
        raise RuntimeError(f"{tag} already exists on the Hub; a release tag is never moved")
    api.create_tag(repo_id=repo, repo_type=rtype, tag=tag,
                   tag_message=f"NepFakeV2 {tag} benchmark release")
    return tag


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ""
    if cmd == "run-tag-name":
        print(run_tag())
        return 0
    if cmd == "hf-tag" and len(argv) == 2:
        print(f"Hugging Face tag {hf_tag(argv[1])} OK")
        return 0
    if cmd == "release-tag":
        print(f"Hugging Face tag {hf_release_tag(argv[1] if len(argv) > 1 else RELEASE_TAG)} OK")
        return 0
    if cmd == "sync-card":
        print("card changed" if sync_card_configs() else "card already up to date")
        return 0
    print("usage: python -m pipeline.versioning run-tag-name | hf-tag <run-YYYY-MM-DD> "
          "| release-tag [vX.Y] | sync-card")
    return 2


if __name__ == "__main__":
    sys.exit(main())
