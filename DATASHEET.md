# NepFakeV2 datasheet (schema 2.0)

Structured after "Datasheets for Datasets" (Gebru et al.). Numbers are for
the 2026-11-23 data (940 rows); `data/stats.json` has the current ones.

## Motivation

- **Purpose.** A real, non-synthetic Nepali fact-checking dataset. Main task:
  tell **FALSE** (मिथ्या: nothing real behind the claim) from **MISLEADING**
  (भ्रामक: something real, twisted) using the claim and the evidence.
- **Creator.** Nandan Singh. No funding.

## Composition

- **Instances.** One row = one fact-check article by TechPana (274) or
  NepalFactCheck (666), from Mar 2020 to the latest weekly scrape.
- **Labels.** The fact-checker's published verdict, not an annotator's
  opinion. Coarse `verdict_label` (REAL / FALSE_MISLEADING / UNVERIFIED) and
  fine `label_fine` (FALSE 336, MISLEADING 538, MIXED 23, TRUE 17,
  UNVERIFIED 26). `label_source` says where each verdict was read.
- **Main benchmark.** `in_main_benchmark`: 830 rows (319 FALSE, 511
  MISLEADING). Left out: TRUE/UNVERIFIED (not the task), MIXED (both labels
  given), `stored` (badge only, until hand-checked), English rows (6).
- **Model inputs.** `claim_text` and `evidence_text`. `headline` and
  `conclusion_text` state the verdict and must not be inputs.
- **Left out entirely.** `data/excluded.csv`: 22 NFC explainers, 4 TechPana
  articles that are not fact-checks. An NFC article tagged both तथ्यजाँच
  and एक्सप्लेनर is a fact-check and is kept (1 so far).
- **Splits.**
  - `split` (time, by the earliest date in a claim group): train to
    2024-12-31, dev 2025, test 2026 onwards. Benchmark rows: train 202 / 131,
    dev 43 / 114, test 74 / 266 (FALSE / MISLEADING).
  - `split_random`: claim groups hashed 70 / 10 / 20.
  - Both are provisional until frozen (`python -m pipeline.splitter freeze`,
    planned after the full re-scrape). After the freeze, `data/splits_v2.0.csv`
    and its sha256 in the manifest fix the splits; new rows get `new`.
- **Redundancy.** URL duplicates are removed (newest snapshot wins).
  The same claim checked by both outlets is kept twice and shares a
  `claim_group_id` (48 groups with 2 or more rows today).

- **Personal and sensitive data.** Rows quote public fact-checks. They
  name public figures (mostly politicians) and link to the posts and
  accounts that spread a claim, some of them private people. No data was
  collected from people directly. Removal on request (GitHub issue with the
  `source_url`).
- **Who labelled.** The fact-checkers' editors (expert-generated); the
  pipeline only reads their published verdict. A hand check of the
  pipeline's reading is planned before the release (`data_validation/`).

## Known problems (read before reporting results)

1. **The label prior moves over time.** Benchmark FALSE share: 61% in train,
   27% in dev, 22% in test. A model can look good on the time split by
   tracking the base rate. Report the random split next to it, and report a
   majority-class baseline per split.
2. **Fact-checkers do not draw the FALSE / MISLEADING line consistently.**
   23 TechPana conclusions name both; summary and conclusion disagree in 9.
   Treat inter-outlet disagreement as a ceiling on accuracy.
3. **Text is cleaned by rules.** Verdict words are removed from
   `claim_text` and `evidence_text`, and a word counter is at the majority
   baseline (tested). Content words that correlate with a label stay on
   purpose (for example "एआई" for FALSE, "पुरानो" for MISLEADING): they are the
   evidence. A character n-gram logistic regression gets macro-F1 0.68 on
   `evidence_text` (0.81 on the old full body), grouped 5-fold.
4. **`claim_text` is extracted, not written by hand.** `lead` 793,
   `lead_quote` 55, `claim_section` 22, `claim_box` 8, `headline` 60
   (fallback). Not yet hand-checked (planned: 50 claims).
5. **Claim groups are a heuristic** (rare shared words, 30 days). One
   election-period group has 38 rows.
6. **`stored` labels (46) are the weakest**; they are out of the benchmark
   until hand-checked.
7. **`topic_category`** is a keyword match on the first 500 characters.
   Use it for description only.

## Collection

- Weekly GitHub Action (Mondays 00:15 UTC): scrapes new articles from both
  sites into `raw/<source>/<date>.json` (never edited afterwards), rebuilds
  `data/`, runs the tests, commits, then pushes to Hugging Face.
- TechPana is behind Cloudflare and is fetched through FlareSolverr.
- Corrections are re-derived from the saved text, never by editing raw files.
  History: `CHANGELOG.md`.

## Preprocessing

- Raw article text is kept unchanged in `raw/`. `data/` is rebuilt from it
  by `python -m pipeline.rebuild`; a test checks that the rebuild gives the
  same bytes.
- Verdict read from the article's own header tag (NFC) or conclusion /
  lead summary (TechPana); `label_source` records which. Verdict words are
  removed from the model inputs. Explainers and non-fact-checks are left out
  and listed in `data/excluded.csv`. Details: `CHANGELOG.md`.

## Uses

- Intended: research on Nepali misinformation, FALSE-vs-MISLEADING
  classification, evidence-based verification, temporal robustness.
- Not intended: judging the truth of new claims in production; profiling
  people named in the claims or linked in `external_evidence_urls`.

## Distribution and maintenance

- GitHub (raw + normalized) and Hugging Face `Nandan007/NepFakeV2`
  (normalized). Data CC BY 4.0 (the source articles belong to TechPana and
  NepalFactCheck; rows link to them), code MIT.
- **Versions** ([VERSIONING.md](VERSIONING.md)): the benchmark is the
  release tag `v2.0` (frozen, never edited); each weekly push is tagged
  `run-YYYY-MM-DD` on GitHub and Hugging Face. Cite the tag
  (`CITATION.cff`), not a download date. Scores: macro-F1 on the v2.0 time
  test split, with the random split and the majority baseline
  (`python -m pipeline.evaluate`).
- **Licence scope.** CC BY 4.0 covers the labels, metadata and structure;
  the quoted article text stays the outlets' copyright.
- Errors: open an issue with the `source_url`. Hand-checked corrections go
  into `data_validation/reference_labels.csv`.
