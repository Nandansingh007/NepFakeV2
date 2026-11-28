"""
Test: hand-checked reference labels (brief: reference-label test).

data_validation/reference_labels.csv does not exist until the hand check is
done. Until then the tests on the real data SKIP, and the mechanism is
tested on a temporary file.

When the file exists:
  - test_pipeline_agrees_with_reference measures the pipeline WITHOUT the
    overrides against your labels: >= 90% agreement on rows whose verdict
    was read from the text. This is the number to report.
  - the overrides are applied (label_source "hand_checked").
"""
import pytest



def load_reference_labels(path=None):
    # imported lazily so this file still collects on code from before 2.0
    from pipeline.reference_labels import load_reference_labels as f
    return f(path)


def _write(tmp_path, text):
    p = tmp_path / "ref.csv"
    p.write_text(text, encoding="utf-8")
    return p


def test_missing_file_means_no_overrides(tmp_path):
    assert load_reference_labels(tmp_path / "nope.csv") == {}


def test_reads_blind_sheet_columns_and_skips_blank(tmp_path):
    p = _write(tmp_path, "url,YOUR_LABEL,note\n"
                         "https://www.techpana.com/2026/1/a/,misleading,\n"
                         "https://techpana.com/2026/2/b,,\n"
                         "https://techpana.com/2026/3/c,BOTH,x\n")
    assert load_reference_labels(p) == {
        "https://techpana.com/2026/1/a": "MISLEADING",
        "https://techpana.com/2026/3/c": "BOTH"}


def test_unknown_label_is_an_error(tmp_path):
    p = _write(tmp_path, "source_url,label\nhttps://techpana.com/2026/1/a,FAKE\n")
    with pytest.raises(ValueError):
        load_reference_labels(p)


def _raw():
    return {"source_name": "nepalfactcheck",
            "source_url": "https://nepalfactcheck.org/2026/01/a/",
            "title": "नेताको भनिएको भिडिओ", "date_published": "2026-01-02",
            "date_scraped": "2026-01-05", "raw_verdict_text": "",
            "body_text": "☰\n×\nभ्रामक सूचना\nनेताको भनिएको भिडिओ\nHome\n"
                         + "सामाजिक सञ्जालमा नेताले भाषण गरेको दाबीसहित भिडिओ भाइरल भएको छ ।\n" * 5}


def test_override_sets_label_and_source():
    from pipeline.normalizer import normalize_article
    ex = normalize_article(_raw(), {"https://nepalfactcheck.org/2026/01/a": "FALSE"})
    assert (ex.label_fine, ex.verdict_label, ex.label_source) == ("FALSE", 1, "hand_checked")
    assert ex.in_main_benchmark is True
    ex = normalize_article(_raw(), {"https://nepalfactcheck.org/2026/01/a": "BOTH"})
    assert (ex.label_fine, ex.in_main_benchmark) == ("MIXED", False)


def test_not_a_factcheck_is_excluded_with_reason():
    from pipeline.normalizer import normalize_article
    out = []
    ex = normalize_article(_raw(), {"https://nepalfactcheck.org/2026/01/a": "NOT_A_FACTCHECK"}, out)
    assert ex is None and out[0]["reason"] == "hand_checked_not_factcheck"


def test_kappa():
    from pipeline.agreement import cohen_kappa
    assert cohen_kappa(["A", "B", "A", "B"], ["A", "B", "A", "B"]) == 1.0
    assert abs(cohen_kappa(["A", "A", "B", "B"], ["A", "B", "A", "B"])) < 1e-9


@pytest.mark.data
def test_pipeline_agrees_with_reference():
    refs = load_reference_labels()
    if not refs:
        pytest.skip("data_validation/reference_labels.csv not filled in yet (hand check)")
    from pipeline.normalizer import normalize_all
    from pipeline.reference_labels import fine_label
    from utils.helpers import canonical_url
    plain = {canonical_url(e.source_url): e for e in normalize_all(references={})}
    pairs = [(plain[u].label_fine, fine_label(r)) for u, r in refs.items()
             if u in plain and r != "NOT_A_FACTCHECK"
             and plain[u].label_source not in ("stored",)]
    if len(pairs) < 20:
        pytest.skip(f"only {len(pairs)} checked text-read rows")
    agree = sum(a == b for a, b in pairs) / len(pairs)
    assert agree >= 0.90, f"pipeline agrees with the hand check on {agree:.1%} of {len(pairs)}"


@pytest.mark.data
def test_overrides_applied(normalized):
    refs = load_reference_labels()
    if not refs:
        pytest.skip("no reference labels yet")
    from pipeline.reference_labels import fine_label
    from utils.helpers import canonical_url
    for e in normalized:
        r = refs.get(canonical_url(e.source_url))
        if r:
            assert (e.label_source, e.label_fine) == ("hand_checked", fine_label(r))
