import json
from pathlib import Path

sources = {
    "techpana": "raw/techpana/2026-09-06.json",
    "nepalfactcheck": "raw/nepalfactcheck/2026-09-06.json",
}

all_data = []

for source_name, path in sources.items():
    p = Path(path)
    if not p.exists():
        print(f"FILE NOT FOUND: {path}")
        continue

    with open(p, 'r', encoding='utf-8') as f:
        data = json.load(f)

    all_data.extend(data)

    print("=" * 50)
    print(f"SOURCE: {source_name.upper()}")
    print("=" * 50)
    print(f"Total records: {len(data)}")

    # Verdict distribution
    verdicts = {}
    for r in data:
        v = r['raw_verdict_text'].strip() if r['raw_verdict_text'] else 'EMPTY'
        verdicts[v] = verdicts.get(v, 0) + 1

    print("Verdict distribution:")
    for v, count in sorted(verdicts.items(), key=lambda x: -x[1]):
        pct = count / len(data) * 100
        print(f"  {v:<25} {count:>4}  ({pct:.1f}%)")

    # Date analysis
    iso_dates = []
    bs_dates = []
    empty_dates = []

    for r in data:
        d = r.get('date_published', '')
        if not d:
            empty_dates.append(d)
        elif d[0].isdigit() and len(d) >= 10:
            iso_dates.append(d[:10])
        elif d[0].isdigit() and len(d) == 4:
            iso_dates.append(f"{d}-01-01")
        else:
            bs_dates.append(d)

    iso_dates.sort()
    print(f"ISO dates:     {len(iso_dates)}")
    print(f"BS dates:      {len(bs_dates)}")
    print(f"Empty dates:   {len(empty_dates)}")
    if iso_dates:
        print(f"ISO range:     {iso_dates[0]} to {iso_dates[-1]}")
    if bs_dates:
        print(f"BS sample:     {bs_dates[0]}")

    # Body text
    body_lengths = [len(r['body_text']) for r in data if r['body_text']]
    print(f"Body text avg: {sum(body_lengths)/len(body_lengths):.0f} chars")
    print(f"Empty bodies:  {sum(1 for r in data if not r['body_text'])}")

    # External links
    total_links = sum(len(r['external_links']) for r in data)
    print(f"Ext links avg: {total_links/len(data):.1f} per article")
    print(f"No links:      {sum(1 for r in data if not r['external_links'])}")
    print()


# Combined verdict to label mapping
VERDICT_TO_LABEL = {
    "भ्रामक":         1,
    "भ्रामक सूचना":   1,
    "मिथ्या":         1,
    "मिथ्या सूचना":   1,
    "अपुष्ट":         2,
    "अपुष्ट सूचना":   2,
    "सही":            0,
    "सही सूचना":      0,
    "गलत":            1,
}

print("=" * 50)
print("COMBINED — ALL SOURCES")
print("=" * 50)
print(f"Total records: {len(all_data)}")
print()

label_counts = {0: 0, 1: 0, 2: 0, "UNMAPPED": 0}
for r in all_data:
    v = r['raw_verdict_text'].strip() if r['raw_verdict_text'] else ''
    label = VERDICT_TO_LABEL.get(v, "UNMAPPED")
    if label not in label_counts:
        label_counts[label] = 0
    label_counts[label] += 1

label_names = {
    0: "REAL",
    1: "FALSE/MISLEADING",
    2: "UNVERIFIED",
    "UNMAPPED": "UNMAPPED (empty/unknown)"
}

print("Label distribution after mapping:")
for label in [0, 1, 2, "UNMAPPED"]:
    count = label_counts[label]
    pct = count / len(all_data) * 100
    print(f"  Label {label} — {label_names[label]:<30} {count:>4}  ({pct:.1f}%)")

print()

# Combined date stats
iso_all = []
bs_all = []
for r in all_data:
    d = r.get('date_published', '')
    if d and d[0].isdigit() and len(d) >= 10:
        iso_all.append(d[:10])
    elif d and not d[0].isdigit():
        bs_all.append(d)

iso_all.sort()
print(f"ISO dates total:  {len(iso_all)}")
print(f"BS dates total:   {len(bs_all)}")
if iso_all:
    print(f"ISO date range:   {iso_all[0]} to {iso_all[-1]}")
print(f"Total sources:    {len(sources)}")
print()
print("Action needed:")
unmapped = label_counts["UNMAPPED"]
if unmapped == 0:
    print(f"  None — all verdicts mapped correctly")
else:
    print(f"  {unmapped} records have empty/unknown verdicts — fix verdict extraction")