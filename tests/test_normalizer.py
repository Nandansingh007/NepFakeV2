"""
Test: pipeline/normalizer.py
Date conversion, plus basic shape checks on normalize_all() over raw/.

NOTE (Phase 0): ported 1:1. The TechPana verdict rule is tested in
test_verdict_resolution.py (Phase 1, fix 1); the explainer check is not yet.
"""
import pytest

from pipeline.normalizer import normalize_date


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-07-14T14:47:19+05:45", "2026-07-14"),  # ISO full datetime
        ("2026-08-25T10:08:00+00:00", "2026-08-25"),
        ("2026-07-14", "2026-07-14"),                 # ISO date only
        ("2026-08", "2026-08-01"),                    # year-month only
        ("2026", "2026-01-01"),                       # year only
        ("भदौ ९, २०८३", "2026-08-25"),                # BS date strings
        ("साउन २८, २०८३", "2026-08-13"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.data
def test_normalize_all_count(normalized):
    assert len(normalized) >= 900, f"normalize_all() returned {len(normalized)}"


@pytest.mark.data
def test_normalize_all_required_fields(normalized):
    # The old script only looked at the first 10 rows; this checks all of them.
    problems = []
    for e in normalized:
        if not e.example_id or not e.example_id.startswith("NF2_"):
            problems.append(f"bad example_id {e.example_id!r}: {e.source_url}")
        if not e.claim_text:
            problems.append(f"missing claim_text: {e.source_url}")
        if e.verdict_label not in (-1, 0, 1, 2):
            problems.append(f"invalid verdict_label {e.verdict_label}: {e.source_url}")
        if not e.source_name:
            problems.append(f"missing source_name: {e.source_url}")
    assert not problems, "\n".join(problems[:20])


@pytest.mark.data
def test_normalize_all_drops_unknown(normalized):
    # validate_batch() inside normalize_all() must drop UNKNOWN (-1) rows
    unknown = [e.source_url for e in normalized if e.verdict_label == -1]
    assert not unknown, f"{len(unknown)} UNKNOWN rows in output: {unknown[:5]}"
