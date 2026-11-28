# pipeline/agreement.py
# =============================================================================
# Label agreement (brief: kappa audit). Compares two label columns for the
# same articles, e.g. the pipeline's label_fine against your hand check, or
# two annotators against each other.
#
#   python -m pipeline.agreement A.csv B.csv
#       A.csv / B.csv: columns source_url (or url) and label (or YOUR_LABEL)
#   python -m pipeline.agreement data_validation/reference_labels.csv
#       one file: compares it with label_fine in data/nepfakev2.csv
#
# Prints n, raw agreement, Cohen's kappa and the confusion table.
# Kappa needs at least ~50 shared items to mean much; it says so.
# =============================================================================

import csv
import sys
from collections import Counter
from pathlib import Path


def cohen_kappa(a: list, b: list) -> float:
    """Cohen's kappa for two equal-length label lists."""
    if len(a) != len(b) or not a:
        raise ValueError("need two non-empty lists of the same length")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[k] * cb.get(k, 0) for k in ca) / (n * n)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _read(path) -> dict:
    from utils.helpers import canonical_url
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        url = (r.get("source_url") or r.get("url") or "").strip()
        lab = (r.get("label") or r.get("YOUR_LABEL") or r.get("label_fine") or "").strip().upper()
        if url and lab:
            out[canonical_url(url)] = {"BOTH": "MISLEADING"}.get(lab, lab)
    return out


def compare(a: dict, b: dict) -> dict:
    keys = sorted(set(a) & set(b))
    la, lb = [a[k] for k in keys], [b[k] for k in keys]
    return {
        "n": len(keys),
        "agreement": sum(x == y for x, y in zip(la, lb)) / len(keys) if keys else 0.0,
        "kappa": cohen_kappa(la, lb) if keys else float("nan"),
        "confusion": Counter(zip(la, lb)),
    }


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__ if __doc__ else "usage: python -m pipeline.agreement A.csv [B.csv]")
        return 2
    a = _read(argv[0])
    b = _read(argv[1] if len(argv) > 1 else Path("data") / "nepfakev2.csv")
    r = compare(a, b)
    print(f"n = {r['n']}   agreement = {r['agreement']:.3f}   kappa = {r['kappa']:.3f}")
    if r["n"] < 50:
        print("note: fewer than 50 shared items, kappa is not reliable")
    for (x, y), c in sorted(r["confusion"].items(), key=lambda t: -t[1]):
        print(f"  {x:<16} {y:<16} {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
