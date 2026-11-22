# Changelog

Changes to the NepFakeV2 normalized dataset (`data/`) and its schema.
The raw layer (`raw/`) is never edited; corrections are re-derived from the
saved article text. Weekly data updates (new articles only) are not listed.

## 1.1 (2026-11-22)

**Schema**
- Added `label_source`: where the verdict was read.
  `nfc_header` (NepalFactCheck header tag), `conclusion` (TechPana conclusion
  names one verdict), `conclusion_mixed` (conclusion names both मिथ्या and
  भ्रामक), `summary` (TechPana lead summary), `stored` (the scraper's stored
  value, usually the image badge).
- `stats.json`: `schema_version` now comes from the code (was hardcoded 1.0);
  new `label_source_distribution`.

**Labels**
- TechPana: the scraper and normalizer now share one rule
  (`scrapers/techpana.py` `resolve_verdict`): conclusion, then lead summary,
  then badge. The scraper used to read the badge first: 54 raw verdicts
  disagreed with the dataset.
- 3 labels changed, all via the lead summary:
  `techpana.com/2025/151229` FALSE_MISLEADING → UNVERIFIED;
  `techpana.com/2025/150099` and `techpana.com/2025/149828`
  UNVERIFIED → FALSE_MISLEADING.
  Totals: REAL 17, FALSE_MISLEADING 895, UNVERIFIED 26.
- "गलत" maps to misleading (was false). No 3-class label changes.

**Unchanged:** example IDs, row count (938), raw files.

## 1.0 (2026-10-11 data corrections)

See "Data corrections" in README.md: NepalFactCheck verdicts from the header
tag (39 fixed), TechPana verdicts from the conclusion (8 labels fixed),
TechPana dates from the article's own date line (145 fixed), explainers and
non-fact-checks excluded.
