"""
Test: no secrets in the repo or its git history.

Why this was rewritten (Phase 0):
The old script searched git history for literal strings such as
'tskey-auth'. Those strings only ever existed inside this test file, so
`git log -S` always found the commit that added the test, and the check
failed on every run. It also called sys.exit() at import time, which
crashed pytest collection.

The new version looks for the *shape* of real tokens with regular
expressions. A regex like  hf_[A-Za-z0-9]{30,}  does not match its own
source text (the '[' breaks it), so this file can never flag itself.
"""
import re
import subprocess
import warnings
from pathlib import Path

import pytest

# Shapes of the token types this project actually uses or could leak.
SECRET_PATTERNS = {
    "huggingface_token": r"hf_[A-Za-z0-9]{30,}",
    "tailscale_key":     r"tskey-[a-z]+-[A-Za-z0-9]{8,}",
    "github_token":      r"gh[pousr]_[A-Za-z0-9]{30,}",
    "github_pat":        r"github_pat_[A-Za-z0-9_]{30,}",
}
COMBINED = "(" + "|".join(SECRET_PATTERNS.values()) + ")"
COMBINED_RE = re.compile(COMBINED)


def _git(*args) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True
    ).stdout


def _in_git_repo() -> bool:
    try:
        return _git("rev-parse", "--is-inside-work-tree").strip() == "true"
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


needs_git = pytest.mark.skipif(not _in_git_repo(), reason="not a git checkout")


@pytest.mark.parametrize(
    "fake",
    [
        # Built at runtime so no token-shaped literal is ever in the source.
        "hf_" + "A1b2" * 9,
        "tskey-" + "auth-" + "kAbC123xyz" * 2,
        "ghp_" + "Z9y8" * 9,
        "github_pat_" + "x" * 40,
    ],
)
def test_patterns_detect_fake_tokens(fake):
    """The detector must actually catch real-looking tokens (no vacuous pass)."""
    assert COMBINED_RE.search(f"token = '{fake}'")


def test_patterns_do_not_match_this_file():
    assert not COMBINED_RE.search(Path(__file__).read_text(encoding="utf-8"))


@needs_git
def test_no_secrets_in_tracked_files():
    hits = []
    for name in _git("ls-files").splitlines():
        p = Path(name)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if COMBINED_RE.search(text):
            hits.append(name)
    assert not hits, f"token-shaped strings found in: {hits}"


@needs_git
def test_no_secrets_in_git_history():
    if _git("rev-parse", "--is-shallow-repository").strip() == "true":
        pytest.skip("shallow clone: history check needs fetch-depth: 0")
    commits = _git("log", "--all", f"-G{COMBINED}", "--format=%h %s").strip()
    assert not commits, f"token-shaped strings were added in:\n{commits}"


@needs_git
def test_env_file_not_tracked():
    assert not _git("ls-files", ".env").strip(), ".env is tracked by git"


def test_gitignore_rules():
    content = Path(".gitignore").read_text()
    for item in [".env", "venv/", "logs/"]:
        assert item in content, f".gitignore missing: {item}"
    # raw/ must be committed: it is the source of truth for the dataset
    assert "raw/" not in content, ".gitignore ignores raw/"


def test_no_unused_scraping_packages():
    content = Path("requirements.txt").read_text()
    unused = [p for p in ["playwright", "playwright-stealth", "curl_cffi"] if p in content]
    if unused:
        warnings.warn(f"unused packages in requirements.txt: {unused}")
