# Changelog

Changes to the NepFakeV2 normalized dataset (`data/`) and its schema.
The raw layer (`raw/`) is never edited; corrections are re-derived from the
saved article text. Weekly data updates (new articles only) are not listed.

## 2.0 (2026-11-23)

Major version: new IDs, a new label definition and new model-input text.
No verdict label changed (same labels as 1.1 on every row that 1.1 kept).
Numbers below are for the 2026-11-23 data: 940 rows, 26 left out.

**Breaking**
- `example_id` is stable and comes from the URL: `NF2_tp_<article number>`
  (TechPana), `NF2_nfc_<10 hex of sha1(canonical URL)>` (NepalFactCheck).
  Before, it was `NF2_<date>_<running number>`, so adding an older raw file
  renumbered rows. Old to new: `data/id_map_v1_to_v2.csv`.
- `claim_text` is the claim taken from the article (lead sentence, quoted
  claim, NFC claim box, or the "दाबी" section), not the fact-checker's
  headline, which usually states the verdict. Fallback: the headline with the
  prefix and verdict words removed. `claim_source` says which.
- `evidence_text` is the article body without header, conclusion, footer and
  sidebar, and without any sentence that states the verdict. A word counter
  (मिथ्या vs भ्रामक) scored 90.3% on the old `evidence_text` (majority
  baseline 61.7%); on the new one it scores 61.8%.
- Removed `evidence_sentences` and `source_outlet` (always empty).
- Hugging Face split renamed `train` → `all` (it always held every row).

**New columns**
- `label_fine`: FALSE / MISLEADING / MIXED / TRUE / UNVERIFIED. Each maps to
  one coarse `verdict_label`; the coarse label is now derived from it.
- `in_main_benchmark`: FALSE or MISLEADING, verdict read from the text (not
  `conclusion_mixed`, not `stored`), and `language == "ne"`.
- `headline`, `conclusion_text` (kept for audits; never model inputs).
- `date_precision` (day / month / year), `date_scraped` (snapshot date),
  `language` (`ne` / `en`). `is_native_nepali` now equals `language == "ne"`.
- `claim_group_id`, `split` (time), `split_random` (random control by claim
  group). Provisional until frozen in `data/splits_v2.0.csv`.

**New files**
- `data/excluded.csv`: every article left out, with the reason (19
  explainers, 4 non-fact-checks). `stats.json` `total_including_unknown` is
  now exported rows + excluded rows (it used to equal the row count).
- `data/id_map_v1_to_v2.csv`, `DATASHEET.md`.

**Pipeline**
- Deduplication keeps the newest snapshot of a URL (was: the first seen) and
  reports label changes; the weekly gate fails if more than 10% of re-scraped
  rows change label.
- `save_raw`: a second scrape on the same day replaces the earlier record of
  the same URL (was: kept the old one).
- Full re-scrape: `python -m pipeline.collector --full`, or the workflow's
  `full_rescrape` option.
- Verdict words: whole words only, a negated TRUE word ("सही होइन") is
  ignored, two different verdicts give no label.
- NFC header tag found as the line above the title (was: fixed line 3).
- NFC explainer rule: a tag line with "एक्सप्लेनर" is an explainer only if it
  has no "तथ्यजाँच" tag. 1 article affected: 1.1 dropped it from the 2026-11-23 weekly data (`ai-generated-false-videos-of-prime-minister-balen-and-other-top-officials`, FALSE).
- External links: share buttons and the outlet's own accounts removed (the
  old first-5 rule kept mostly those); up to 20 links.
- Hand-checked labels from `data_validation/reference_labels.csv` override
  the pipeline (`label_source = hand_checked`) once that file exists.
- Hugging Face push is one atomic commit and includes the new files.
- The weekly job and `python -m pipeline.rebuild` share `build_dataset()`;
  a test checks that rebuilding reproduces `data/` byte for byte.
- `python -m pipeline.agreement` computes agreement and Cohen's kappa.

**Versions and tags** ([VERSIONING.md](VERSIONING.md))
- Release tag `v2.0` (git and Hugging Face) marks the benchmark; made once,
  after the freeze. `DATASET_VERSION` in `config/settings.py` names it and is
  separate from `SCHEMA_VERSION`.
- Every successful weekly push is tagged `run-YYYY-MM-DD` on GitHub and on
  Hugging Face (new workflow step after the Hub push).
- `python -m pipeline.splitter release` writes `data/v2.0/` once (refuses to
  overwrite), only frozen rows, plus `RELEASE.json`; sets the release date in
  `CITATION.cff`. The Hugging Face card gets `benchmark-v2.0` and
  `benchmark-v2.0-random` configs only when that folder exists.
- `python -m pipeline.versioning release-tag` tags the Hub only if it already
  holds the same release files.
- Official scorer: `python -m pipeline.evaluate` (macro-F1, FALSE vs
  MISLEADING, majority baseline printed next to it).
- Card metadata: `task_ids`, `annotations_creators`, `language_creators`;
  licence scope and personal-information sections; one citation title.

**Main benchmark** on the 2026-11-23 data: 830 rows (319 FALSE, 511
MISLEADING). Time split: train (to 2024) 202 / 131, dev (2025) 43 / 114,
test (2026) 74 / 266 (FALSE / MISLEADING). `label_source`: nfc_header 663,
conclusion 191, stored 46, conclusion_mixed 23, summary 17. Left out
(`data/excluded.csv`): 22 NFC explainers, 4 TechPana non-fact-checks.

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
