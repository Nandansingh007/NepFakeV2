# pipeline/evaluate.py
# =============================================================================
# Official scorer for the NepFakeV2 benchmark (FALSE vs MISLEADING).
#
#   python -m pipeline.evaluate predictions.csv              # time test split
#   python -m pipeline.evaluate predictions.csv --random     # random control
#   python -m pipeline.evaluate predictions.csv --split dev
#
# predictions.csv: columns example_id, prediction (FALSE or MISLEADING),
# one row per example of the chosen split. A missing, extra or unknown row is
# an error: a score on a different set of rows is not comparable.
#
# The gold file is the release file (data/v2.0/test.csv ...), so a score is
# always tied to a version. Report: version, split, macro-F1, and the
# majority baseline printed next to it.
# =============================================================================

import argparse
import csv
import sys
from pathlib import Path

from config.settings import RELEASE_DIR, RELEASE_TAG

LABELS = ("FALSE", "MISLEADING")


def _read(path: Path, col: str) -> dict:
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if rows and ("example_id" not in rows[0] or col not in rows[0]):
        raise ValueError(f"{path} needs columns example_id and {col}")
    out = {}
    for r in rows:
        if r["example_id"] in out:
            raise ValueError(f"{path}: example_id {r['example_id']} appears twice")
        out[r["example_id"]] = r[col].strip()
    return out


def scores(gold: dict, pred: dict) -> dict:
    """Accuracy, per-class F1, macro-F1 and the majority baseline."""
    missing, extra = sorted(set(gold) - set(pred)), sorted(set(pred) - set(gold))
    if missing or extra:
        raise ValueError(f"predictions must cover exactly the gold rows: "
                         f"{len(missing)} missing (e.g. {missing[:3]}), "
                         f"{len(extra)} extra (e.g. {extra[:3]})")
    bad = sorted({p for p in pred.values() if p not in LABELS})
    if bad:
        raise ValueError(f"unknown prediction labels {bad}; allowed: {LABELS}")
    f1 = {}
    for lab in LABELS:
        tp = sum(1 for k in gold if gold[k] == lab and pred[k] == lab)
        fp = sum(1 for k in gold if gold[k] != lab and pred[k] == lab)
        fn = sum(1 for k in gold if gold[k] == lab and pred[k] != lab)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1[lab] = 2 * p * r / (p + r) if p + r else 0.0
    n = len(gold)
    counts = {lab: sum(1 for v in gold.values() if v == lab) for lab in LABELS}
    major = max(counts, key=counts.get)
    # majority baseline: always predict the most frequent gold class
    base_f1 = (2 * counts[major] / (counts[major] + n)) / len(LABELS) if n else 0.0
    return {
        "n": n,
        "counts": counts,
        "accuracy": sum(1 for k in gold if gold[k] == pred[k]) / n if n else 0.0,
        "f1": f1,
        "macro_f1": sum(f1.values()) / len(LABELS),
        "majority_macro_f1": base_f1,
        "majority_accuracy": counts[major] / n if n else 0.0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score predictions on the NepFakeV2 benchmark")
    ap.add_argument("predictions")
    ap.add_argument("--split", default="test", choices=("train", "dev", "test"))
    ap.add_argument("--random", action="store_true", help="use the random control split")
    ap.add_argument("--release-dir", default=str(RELEASE_DIR))
    a = ap.parse_args(argv)
    rdir = Path(a.release_dir)
    gold_path = rdir / f"{'random_' if a.random else ''}{a.split}.csv"
    if not gold_path.exists():
        print(f"{gold_path} not found: the benchmark is not released yet "
              f"(scores on provisional splits must not be reported)")
        return 2
    s = scores(_read(gold_path, "label_fine"), _read(Path(a.predictions), "prediction"))
    version = rdir.name if rdir.name.startswith("v") else RELEASE_TAG
    split = f"{'random ' if a.random else 'time '}{a.split}"
    print(f"NepFakeV2 {version}, {split} split, {s['n']} rows "
          f"(FALSE {s['counts']['FALSE']}, MISLEADING {s['counts']['MISLEADING']})")
    print(f"  macro-F1  {s['macro_f1']:.4f}   (majority baseline {s['majority_macro_f1']:.4f})")
    print(f"  accuracy  {s['accuracy']:.4f}   (majority baseline {s['majority_accuracy']:.4f})")
    print(f"  F1 FALSE {s['f1']['FALSE']:.4f}  F1 MISLEADING {s['f1']['MISLEADING']:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
