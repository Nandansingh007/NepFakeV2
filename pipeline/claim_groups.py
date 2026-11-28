# pipeline/claim_groups.py
# =============================================================================
# Claim groups (brief: split leakage). TechPana and NepalFactCheck often check
# the same viral post within days of each other; sometimes one outlet checks
# a claim twice. Such rows must never sit in different splits, or a model is
# tested on a claim it was trained on.
#
# Rule: two rows are in one group when they were published at most
# CLAIM_GROUP_MAX_DAYS apart and their word sets (claim + headline, verdict
# and function words removed) overlap: the rare-word weight they share is
# >= CLAIM_GROUP_MIN_SIMILARITY of the smaller set and >=
# CLAIM_GROUP_MIN_SHARED_WEIGHT in total.
# Erring towards grouping is the safe side: an extra link only keeps two
# unrelated rows in the same split; a missed link is leakage. Groups are closed under this link
# (union-find), and claim_group_id is "G_" + the smallest example_id in the
# group, so it does not depend on row order.
#
# This is a heuristic. Its known pairs are tested; report the group count.
# =============================================================================

import re
from datetime import date

from config.settings import (CLAIM_GROUP_MAX_DAYS, CLAIM_GROUP_MIN_SIMILARITY,
                             CLAIM_GROUP_MIN_SHARED_WEIGHT)
from pipeline.text_rules import CUE_WORDS, VERDICT_WORDS

STOP = set(VERDICT_WORDS + CUE_WORDS + """
दाबी दावी भन्दै भनिएको भाइरल भिडिओ भिडियो तस्बिर फोटो सामाजिक सञ्जाल सञ्जालमा
फ्याक्टचेक टेकपाना तथ्य जाँच होइन हो छ छन् को का की ले मा र पनि यो त्यो उक्त
एउटा एक गरेको भएको गरी गर्दै सहित दाबीसहित पोस्ट शेयर सेयर फैलिएको फैलाइएको
एआई निर्मित पुरानो वास्तविक
""".split())
TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z]+|\d+")
SUFFIXES = ("हरूको", "हरुको", "हरू", "हरु", "लाई", "बाट", "सँग", "को", "का", "की",
            "ले", "मा", "मै", "भित्र")


def _stem(tok: str) -> str:
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) > len(suf) + 2:
            return tok[: -len(suf)]
    return tok


def claim_tokens(text: str) -> frozenset:
    toks = (_stem(t.lower()) for t in TOKEN.findall(text or ""))
    return frozenset(t for t in toks if t not in STOP and len(t) > 1)


def _weights(token_sets) -> dict:
    """Inverse document frequency: rare words (names, places) count most."""
    import math
    df = {}
    for toks in token_sets:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    n = max(len(token_sets), 1)
    return {t: math.log(n / c) for t, c in df.items()}


def similarity(a: frozenset, b: frozenset, idf: dict) -> tuple[float, float]:
    """(overlap, shared weight): weight of shared words / weight of the
    smaller set. Overlap, not Jaccard, because one outlet's claim is often
    much longer than the other's."""
    shared = sum(idf.get(t, 0.0) for t in a & b)
    smaller = min(sum(idf.get(t, 0.0) for t in a), sum(idf.get(t, 0.0) for t in b))
    return (shared / smaller if smaller else 0.0), shared


def _days(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return 10 ** 6


def find_groups(examples, max_days: int = CLAIM_GROUP_MAX_DAYS,
                min_sim: float = CLAIM_GROUP_MIN_SIMILARITY,
                min_shared: float = CLAIM_GROUP_MIN_SHARED_WEIGHT) -> dict:
    """{example_id: claim_group_id} for every example."""
    rows = [(e.example_id, e.date_published or "",
             claim_tokens(e.claim_text + " " + e.headline)) for e in examples]
    idf = _weights([r[2] for r in rows])
    rows.sort(key=lambda r: (r[1], r[0]))
    parent = {r[0]: r[0] for r in rows}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, (id_a, d_a, t_a) in enumerate(rows):
        if not d_a:
            continue                        # no date: never grouped
        for id_b, d_b, t_b in rows[i + 1:]:
            if _days(d_a, d_b) > max_days:
                break                       # rows are sorted by date
            overlap, shared = similarity(t_a, t_b, idf)
            if overlap >= min_sim and shared >= min_shared:
                ra, rb = find(id_a), find(id_b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)

    members = {}
    for ex_id in parent:
        members.setdefault(find(ex_id), []).append(ex_id)
    out = {}
    for ids in members.values():
        gid = "G_" + min(ids).removeprefix("NF2_")
        for ex_id in ids:
            out[ex_id] = gid
    return out
