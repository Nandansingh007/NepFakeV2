"""
Test: pipeline/label_mapper.py
Verifies verdict strings map to the expected labels.

NOTE (Phase 0): these cases are copied 1:1 from the old script. They are
happy-path only. In particular "भ्रम" -> 1 and "गलत" -> 1 encode the current
FALSE/MISLEADING merge; revisit them when the label scheme changes (Phase 1).
"""
import pytest

from pipeline.label_mapper import map_verdict, is_mappable


@pytest.mark.parametrize(
    "verdict, expected_label",
    [
        # Label 1 — FALSE/MISLEADING
        ("मिथ्या", 1),
        ("मिथ्या सूचना", 1),
        ("भ्रामक", 1),
        ("भ्रामक सूचना", 1),
        ("झुटो", 1),
        ("गलत", 1),
        ("असत्य", 1),
        ("भ्रम", 1),
        # Label 0 — REAL
        ("सही", 0),
        ("सही सूचना", 0),
        ("साँचो", 0),
        ("सत्य", 0),
        # Label 2 — UNVERIFIED
        ("अपुष्ट", 2),
        ("अपुष्ट सूचना", 2),
        # Label -1 — UNKNOWN
        ("", -1),
        ("   ", -1),
    ],
)
def test_map_verdict(verdict, expected_label):
    label, name = map_verdict(verdict)
    assert label == expected_label, f"map_verdict({verdict!r}) = {label} ({name})"


@pytest.mark.parametrize(
    "verdict, expected",
    [("भ्रामक", True), ("", False), ("unknown garbage", False)],
)
def test_is_mappable(verdict, expected):
    assert is_mappable(verdict) is expected
