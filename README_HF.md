---
license: cc-by-4.0
task_categories:
- text-classification
task_ids:
- fact-checking
annotations_creators:
- expert-generated
language_creators:
- found
language:
- ne
tags:
- fact-checking
- misinformation
- fake-news
- nepali
- low-resource
- nlp
pretty_name: NepFakeV2
size_categories:
- 1K<n<10K
source_datasets:
- original
multilinguality:
- monolingual
configs:
- config_name: default
  default: true
  data_files:
  - split: all
    path: data/nepfakev2.csv
# RELEASE_CONFIGS_START (written by pipeline/versioning.py; empty until the first release)
# RELEASE_CONFIGS_END
---

# NepFakeV2 🇳🇵

The first real, non-synthetic Nepali fact-checking dataset. Built directly from verified fact-checks published by professional Nepali fact-checkers — not machine-translated, not LLM-generated.

## Why This Dataset Exists

All existing Nepali fake news datasets fail in one of two ways:
- **Machine-translated US political content** — introduces topic-domain confounds and MT artifacts. Models learn to detect translation, not misinformation.
- **LLM-generated examples** — do not reflect real misinformation that actually circulated in Nepal.

NepFakeV2 breaks this cycle by sourcing directly from two active IFCN-adjacent Nepali fact-checkers. It grows automatically — new fact-checks are scraped, normalized, and pushed to this repository every week.

## Load the Dataset

```python
from datasets import load_dataset

ds = load_dataset("Nandan007/NepFakeV2")
rows = ds["all"]          # every row; the benchmark splits are columns
train = rows.filter(lambda r: r["in_main_benchmark"] and r["split"] == "train")
```

The Hub split is called `all` (before 2.0 it was `train`, which was misleading: it held every row). The real splits are the `split` (time) and `split_random` (control) columns.

Or load directly as a DataFrame:

```python
import pandas as pd

df = pd.read_csv(
    "https://huggingface.co/datasets/Nandan007/NepFakeV2/resolve/main/data/nepfakev2.csv"
)
```

## Dataset Summary

| | |
|---|---|
| Language | Nepali (Devanagari script) |
| Task | Fact verification / misinformation detection |
| Labels | 3 coarse (REAL, FALSE_MISLEADING, UNVERIFIED) + 5 fine (`label_fine`) |
| Sources | 2 (TechPana, NepalFactCheck) |
| Updates | Weekly — auto-synced from GitHub |
| Schema version | 2.0 |

## Labels

| Label | Int | Description |
|-------|-----|-------------|
| REAL | 0 | Verified factual — confirmed by fact-checkers |
| FALSE_MISLEADING | 1 | Debunked — false or misleading content |
| UNVERIFIED | 2 | Cannot be confirmed or denied |

**Fine labels (`label_fine`, schema 2.0).** The coarse label above is kept unchanged. `label_fine` splits FALSE_MISLEADING:

| `label_fine` | Nepali verdict | Meaning | Coarse label |
|---|---|---|---|
| FALSE | मिथ्या (also झुटो, असत्य) | The claim is fabricated or untrue | 1 |
| MISLEADING | भ्रामक (also भ्रम, गलत) | Real content in a wrong context, or a distorted claim | 1 |
| MIXED | both मिथ्या and भ्रामक | The TechPana conclusion names both; no single fine label | 1 |
| TRUE | सही (also साँचो, सत्य) | The claim is accurate | 0 |
| UNVERIFIED | अपुष्ट | Could not be confirmed or refuted | 2 |

### What the data supports

Every row is one professional fact-check of a claim that circulated in Nepal. Each row has the claim, the article's evidence, the verdict, who made the claim (when the outlet names them), the outlet, the URL and the date. The data can be used for:

- **Falsity type: FALSE vs MISLEADING.** Rows with `in_main_benchmark == True`: fine label FALSE or MISLEADING, verdict read from the article text (or hand-checked), article in Nepali. MIXED rows, badge-only rows (`label_source == "stored"`) and the English rows are left out. Almost every row is a debunk (TRUE 17, UNVERIFIED 26), so this asks *how* a claim is wrong, not *whether* it is.
- **Claim + evidence.** `claim_text` with `evidence_text` (the article's own reasoning, verdict sentences removed).
- **Claim only.** `claim_text` alone. On FALSE vs MISLEADING this is much harder: the difference usually lies in what the media really is (old, edited, from elsewhere), which the claim does not say.
- **Claimant.** `claimant`: who made the claim, as the fact-checker names it (NepalFactCheck rows).
- **Explanations.** `conclusion_text` and the fact-checker's "तथ्य" line state the verdict and why. Use them as targets for explanation generation, never as model inputs for classification.

**The official benchmark task, split and metric are not fixed yet.** They will be fixed at the v2.0 freeze and written here and in [VERSIONING.md](VERSIONING.md). Until then, `in_main_benchmark`, `split` and `split_random` are provisional, and no score on them is official.

**Model inputs: `claim_text` and `evidence_text` only.** `headline` and `conclusion_text` state the verdict. A word counter that counts मिथ्या vs भ्रामक scored 90% on the old `evidence_text`; on the 2.0 columns it scores the majority baseline (62%). If you use the provisional splits, report both: `split` (time) and `split_random` (random by claim group). The FALSE/MISLEADING balance changes a lot between years (train 61% FALSE, test 22% FALSE), so the time split alone mostly measures that shift.

```python
main = df[df["in_main_benchmark"]]               # provisional until the v2.0 freeze
train = main[main["split"] == "train"]          # or split_random
X, y = train["claim_text"] + " " + train["evidence_text"], train["label_fine"]
```

> **On label imbalance:** 90%+ of examples are FALSE_MISLEADING. This reflects real-world distribution — fact-checkers publish mostly debunks by design. This is not a collection error.

## Data Sources

| Source | Type | Language | Coverage |
|--------|------|----------|----------|
| [TechPana](https://techpana.com/factcheck/) | IFCN-certified fact-checker | Nepali | Feb 2025 → present |
| [NepalFactCheck](https://nepalfactcheck.org) | Non-profit fact-checker (CMR-Nepal) | Nepali | Mar 2020 → present |

## Data contract

- **Raw** (`raw/`): a faithful copy of each fetch, never edited afterwards.
- **Normalized** (`data/nepfakev2.csv`): every row passes the written rules, and weaker rows are flagged (`verified`, `label_source`, `snapshot_conflict`).
- **Excluded** (`data/excluded.csv`): every article left out, with a reason.
- **Benchmark** (`in_main_benchmark`): a subset by a written rule, and every other row says why in `benchmark_exclusion_reason`.
- **Count:** unique articles in raw = normalized + excluded, checked by a test on every run.

Details and the exact reasons: the DATASHEET in the GitHub repository, "Data contract".

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `example_id` | string | Stable ID from the URL: `NF2_tp_<article number>` (TechPana) or `NF2_nfc_<10 hex>` (NepalFactCheck). Old IDs (`NF2_YYYYMMDD_NNNN`): `data/id_map_v1_to_v2.csv` |
| `claim_text` | string | The claim being checked, taken from the article: NepalFactCheck's summary box (`दावी :`), a `के … हो?` headline, or the post's caption quoted in TechPana's `दाबी` section; hand-written where the rules fail. Verdict words removed. See `claim_source` |
| `claim_source` | string | Where `claim_text` came from: `claim_box` (NFC summary box), `headline_question` (NFC `के … हो?` headline), `claim_caption` (TechPana: the post's quoted caption), `hand_checked` (`data_validation/claims_reference.csv`), or the fallbacks `lead_quote`, `lead`, `claim_section`, `headline` |
| `claimant` | string | Who made the claim, as the fact-checker names it (NFC `दावीकर्ता`, 74% of NFC benchmark rows; TechPana only from the hand check). Empty if not given |
| `claim_platform` | string | Where the claim spread (several values are separated by a vertical bar): `facebook`, `tiktok`, `x`, `youtube`, `instagram`, `messaging`, `news_media`. From the claimant line and TechPana's `दाबी` section, or the hand check. Empty = the article names none |
| `headline` | string | The fact-checker's headline. **Usually states the verdict: not a model input** |
| `verdict_label` | int | 0 / 1 / 2 (coarse label) |
| `verdict_label_text` | string | REAL / FALSE_MISLEADING / UNVERIFIED |
| `label_fine` | string | FALSE / MISLEADING / MIXED / TRUE / UNVERIFIED (see Labels) |
| `label_source` | string | Where the verdict was read: `nfc_header`, `conclusion`, `conclusion_mixed`, `summary`, `stored` (scraper's badge only), `hand_checked` (a person read the article) |
| `verified` | string | `gold`: a person checked the label (`label_source == "hand_checked"`). `silver`: read from the article by rules only. Score gold rows with `python -m pipeline.evaluate … --gold` |
| `snapshot_conflict` | bool | `True` if another snapshot of the same article had a different `label_fine`. The copy used is chosen by a fixed rule (DATASHEET, "Redundancy") and used whole |
| `snapshot_other_label` | string | `label_fine` of the other snapshot(s), several separated by a vertical bar; empty if none |
| `in_main_benchmark` | bool | True if the row belongs to the main FALSE-vs-MISLEADING task |
| `benchmark_exclusion_reason` | string | Why the row is not in the benchmark, empty if it is: `label_<LABEL>`, `label_source_stored`, `label_source_conclusion_mixed`, `language_en`, `page_cut` (several separated by a vertical bar) |
| `evidence_text` | string | Article body without header, conclusion (TechPana `निष्कर्ष`, NepalFactCheck's `दावी / दावीकर्ता / तथ्य` summary box), footer, and without any sentence that states the verdict |
| `conclusion_text` | string | The fact-checker's conclusion. **States the verdict: not a model input** |
| `external_evidence_urls` | string | Links in the article, `" \| "`-separated, without share buttons and the outlet's own pages |
| `source_name` | string | techpana / nepalfactcheck |
| `source_type` | string | fact_checker |
| `source_url` | string | Original article URL |
| `date_published` | string | ISO date YYYY-MM-DD |
| `date_precision` | string | day / month / year (a year-only date is stored as YYYY-01-01) |
| `date_scraped` | string | Date of the snapshot this row was built from |
| `language` | string | `ne` or `en` (share of Devanagari letters) |
| `is_native_nepali` | bool | `language == "ne"` |
| `label_basis` | string | fact_checker_verdict |
| `topic_category` | string | Keyword heuristic: politics / health / technology / society / environment / economy / other |
| `annotator_notes` | string | Edge-case flags, empty if clean |
| `claim_group_id` | string | Rows about the same claim (often both outlets checking one viral post) share this ID |
| `split` | string | Time split: train / dev / test (`new` for rows added after the freeze) |
| `split_random` | string | Random control split by claim group |
| `schema_version` | string | 2.0 |

## Changes

**2026-11-23, schema 2.0** (breaking: new IDs, new text columns)
- `example_id` is now stable and taken from the URL. Old IDs: `data/id_map_v1_to_v2.csv`.
- `claim_text` is the claim from the article, not the headline. The headline is in `headline`.
- `evidence_text` no longer contains the verdict; the conclusion is in `conclusion_text`. Neither `headline` nor `conclusion_text` is a model input.
- New columns: `label_fine`, `in_main_benchmark`, `claim_source`, `date_precision`, `date_scraped`, `language`, `claim_group_id`, `split`, `split_random`. Removed: `evidence_sentences`, `source_outlet` (always empty).
- The Hub split is now `all` (was `train`).
- Left-out articles (explainers, non-fact-checks) are listed in `data/excluded.csv`.
- An article tagged both तथ्यजाँच (fact-check) and एक्सप्लेनर (explainer) is now kept as a fact-check (1 article, FALSE).
- No verdict label changed.

**2026-11-22, schema 1.1**
- New column `label_source`: where each verdict was read (see Data Fields). `stored` rows (46) carry the scraper's image badge rather than a verdict read from the article text; treat them as less reliable.
- TechPana verdicts now follow one rule: the conclusion box, then the lead summary, then the badge. 3 labels changed: `151229` FALSE_MISLEADING → UNVERIFIED; `150099` and `149828` UNVERIFIED → FALSE_MISLEADING.
- Example IDs and row count (938) are unchanged.

Full history: [CHANGELOG.md on GitHub](https://github.com/Nandansingh007/NepFakeV2/blob/main/CHANGELOG.md).

## Dataset Statistics

See [stats.json](https://huggingface.co/datasets/Nandan007/NepFakeV2/resolve/main/data/stats.json) for live statistics updated after every pipeline run.

## Limitations

- **Label imbalance** — fact-checkers publish mostly debunks by design. 90%+ FALSE_MISLEADING reflects real-world distribution, not a collection error.
- **claim_text**: on the benchmark, 524 rows come from NepalFactCheck's summary box and 49 from its `के … हो?` headlines. The other 257 (all TechPana rows, mostly 2020 NepalFactCheck rows) are being checked by hand. Until then, treat `claim_caption` and the fallback sources as weaker.
- **Splits are provisional** until frozen in `data/splits_v2.0.csv`. Do not report numbers on provisional splits.
- **Cross-source duplicates** — the same claim may be fact-checked by both sources independently. Both records are retained and share `claim_group_id`; the splits never separate a group. The grouping is a heuristic (shared rare words within 30 days).

## Versions and how to report results

- **Live data** (`default` config, `main`): grows every week. Every weekly push is tagged `run-YYYY-MM-DD` here and on GitHub. Do not report benchmark scores on it.
- **Benchmark `v2.0`**: frozen splits, released once (planned after the full re-scrape and the hand check). After the release: `load_dataset("Nandan007/NepFakeV2", "benchmark-v2.0", revision="v2.0")`, plus `benchmark-v2.0-random` for the control split. Until then those configs do not exist.
- **Every published score names the release and the split**, e.g. "NepFakeV2 v2.0, time test split". The official task, split and metric are fixed at the v2.0 freeze (see [What the data supports](#what-the-data-supports)); always report the majority baseline next to a score. Scorer: `python -m pipeline.evaluate` in the GitHub repo.
- **Cite the tag** (`v2.0`, or a `run-` tag for live data), not a download date.
- Rows added after the freeze have `split = "new"`. You may split them as you like; we recommend splitting by `claim_group_id`, dropping new rows whose `claim_group_id` is also in v2.0 if you train on v2.0, and reporting the run tag and the `date_published` range you used.
- When a new version comes out, and everything above in detail: [VERSIONING.md](VERSIONING.md).

## Personal and sensitive information

Rows quote public fact-checks. They name public figures (mostly politicians) and link to the social-media posts and accounts that spread a claim, some of them private people. The `claimant` column repeats the names the fact-checker gives for who spread a claim (pages, accounts, sometimes private users). Do not use the data to profile or target anyone named or linked. To have a row removed, open an issue on GitHub with its `source_url`.

## Citation

Cite the release tag you used (`v2.0`), not the download date. `CITATION.cff` in the repo has the same metadata.

```bibtex
@dataset{singh2026nepfakev2,
  author    = {Singh, Nandan},
  title     = {NepFakeV2: A Live, auto-updating Dataset for Nepali Misinformation Detection},
  version   = {v2.0},
  year      = {2026},
  publisher = {Hugging Face},
  url       = {https://huggingface.co/datasets/Nandan007/NepFakeV2},
  note      = {Benchmark release v2.0. For live data, give the run-YYYY-MM-DD tag instead.}
}
```

## License

- **Data**: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Code**: [MIT](https://github.com/Nandansingh007/NepFakeV2/blob/main/LICENSE)

The CC BY 4.0 licence covers the labels, the metadata and the dataset's structure. The article text in `claim_text`, `evidence_text`, `headline` and `conclusion_text` is quoted from TechPana and NepalFactCheck, who keep its copyright; every row links to the original article. Rights holders can ask for removal through a GitHub issue.

## Links

- GitHub: [github.com/Nandansingh007/NepFakeV2](https://github.com/Nandansingh007/NepFakeV2)
- Pipeline: see `scrapers/`, `pipeline/` in the GitHub repo