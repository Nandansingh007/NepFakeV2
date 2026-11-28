# NepFakeV2 Annotation Guidelines

**Version:** 2.0 (schema 2.0)
**Last updated:** 23 November 2026

These guidelines cover two things: how the pipeline reads each verdict, and how a person checks or audits a label by hand (the reference-label check and the agreement / kappa audit).

---

## 1. The gold label is the fact-checker's verdict

Every label in NepFakeV2 is **the verdict the fact-checker published**. It is not the annotator's opinion, and it is not based on source credibility (`label_basis` is always `fact_checker_verdict`).

When you check a label by hand, the question is **"what did the fact-checker conclude?"**, not "what do I think is true?". If you disagree with the fact-checker, record the verdict they gave as the label and put your own view in the note column. The audit uses those notes separately.

---

## 2. Sources

| Source | URL | Where the verdict is |
|--------|-----|----------------------|
| TechPana | [techpana.com/factcheck](https://techpana.com/factcheck/) | The `निष्कर्ष` (conclusion) box at the end; a one-sentence finding in the lead summary; a badge in the share image |
| NepalFactCheck | [nepalfactcheck.org](https://nepalfactcheck.org) | A header tag above the headline, e.g. `भ्रामक सूचना` |

NepalFactCheck explainers (header tag `एक्सप्लेनर`) explain a topic and check no claim. They get no label and are excluded.

---

## 3. How the pipeline reads a verdict (`label_source`)

| Source | Order (first match wins) | `label_source` |
|---|---|---|
| NepalFactCheck | header tag names one verdict | `nfc_header` |
| | otherwise: the value the scraper stored | `stored` |
| TechPana | the conclusion names exactly one verdict | `conclusion` |
| | the conclusion names both मिथ्या and भ्रामक | `conclusion_mixed` |
| | the lead summary's finding sentence names one verdict | `summary` |
| | otherwise: the value the scraper stored (the image badge) | `stored` |
| any | a person checked it (`data_validation/reference_labels.csv`) | `hand_checked` (overrides all of the above) |

Word rules (`scrapers/techpana.py`, `pipeline/label_mapper.py`):
- Whole words only. `भ्रम` does not match `भ्रमण` (travel).
- A negated "true" is not a verdict: "सही होइन", "सत्य छैन" and similar are ignored.
- If a verdict text names two different verdicts, it gets no label (it is not "first word wins").
- `गलत` (wrong) counts as MISLEADING. Fact-checkers mostly use it in "गलत सन्दर्भ" (wrong context).
- Known weakness: `भ्रम` also matches the phrase "भ्रम फैलाइएको" (spread confusion), which is not a verdict. It can make a conclusion look mixed.

`stored` labels are the weakest. For TechPana files scraped before 12 Oct 2026, the stored badge may even belong to a different article in the sidebar.

---

## 4. Labels

### 4.1 Coarse label (`verdict_label`, unchanged since 1.0)

| Int | `verdict_label_text` | Meaning |
|---|---|---|
| 0 | REAL | Verified as accurate |
| 1 | FALSE_MISLEADING | Debunked: false or misleading |
| 2 | UNVERIFIED | Could not be confirmed or refuted |

### 4.2 Fine label (`label_fine`, new in 2.0)

| `label_fine` | Nepali verdicts | Coarse |
|---|---|---|
| FALSE | मिथ्या, मिथ्या सूचना, झुटो, असत्य | 1 |
| MISLEADING | भ्रामक, भ्रामक सूचना, भ्रम, गलत | 1 |
| MIXED | the TechPana conclusion names both मिथ्या and भ्रामक | 1 |
| TRUE | सही, सही सूचना, साँचो, सत्य | 0 |
| UNVERIFIED | अपुष्ट, अपुष्ट सूचना | 2 |

Each fine label maps to exactly one coarse label. The validator rejects a record where they disagree.

### 4.3 FALSE vs MISLEADING: the definition

Use this when the fact-checker's own wording is unclear (see section 5), and when you write your own view in the audit.

**FALSE (मिथ्या):** the core of the claim did not happen or was never said.
- The event did not happen (for example, "X was arrested" when no arrest took place).
- The quote, post, letter or document was never made, or is forged (a fake screenshot or a fabricated notice).
- The image, video or audio is fully synthetic (AI-generated, a deepfake) and is presented as real.

**MISLEADING (भ्रामक):** something real is presented so that people believe something untrue.
- Real footage or photos from another time or place ("an old flood video shared as today's").
- A real event, but the claim gets a key detail wrong: place, number, cause or person ("death at the counting centre" when the death was real but elsewhere).
- Real material that has been edited, clipped or cropped to change its meaning.
- Exaggeration, or a partial truth stated as the whole truth. Satire shared as news.

**Rule of thumb:** ask "is there a real original behind this?" If there is no real original, the label is FALSE. If there is a real original that was twisted, the label is MISLEADING.

**Be honest about the ceiling.** The fact-checkers do not apply this line consistently. In 9 TechPana articles the summary and the conclusion give different verdicts, and 23 conclusions name both. A model's FALSE-vs-MISLEADING score has a ceiling set by this disagreement. Report it.

### 4.4 MIXED

MIXED means the fact-checker named both labels in the conclusion (for example "दाबी पूर्णतः भ्रामक र मिथ्या हो"). Do **not** pick one using the summary or the badge. The row keeps the coarse label FALSE_MISLEADING and is left out of the main benchmark.

### 4.5 UNKNOWN (-1) and explainers: dropped

- **UNKNOWN (-1):** the verdict could not be mapped. The record is **dropped** from `data/` by the validator. It is **not** kept in the dataset (version 1.0 of these guidelines was wrong about this). The normalizer logs the URL with the note `verdict_unmappable`, and the raw text stays in `raw/`.
- **Explainers:** dropped, with the note `explainer_not_factcheck`.

---

## 5. Main benchmark (`in_main_benchmark`)

The main task is binary FALSE vs MISLEADING. A row is in it when:
1. `label_fine` is FALSE or MISLEADING, **and**
2. `label_source` is not `conclusion_mixed` and not `stored`. The verdict must have been read from the article text (or checked by a person), **and**
3. `language` is `ne`. The few English TechPana articles are left out.

Excluded rows stay in the dataset with `in_main_benchmark = False`. TRUE and UNVERIFIED are excluded because the task is binary. `stored` rows can come back once a person has checked them (section 6).

The list of excluded sources is in `config/settings.py` (`BENCHMARK_EXCLUDED_SOURCES`).

---

## 6. Checking labels by hand

1. **Work blind.** Use the sheet without the current label. Seeing the pipeline's answer anchors you.
2. Open the article (the URL). Read the conclusion first, then the lead summary.
3. Write one of: `FALSE`, `MISLEADING`, `TRUE`, `UNVERIFIED`, `BOTH` (the fact-checker gave both), `NOT_A_FACTCHECK`.
4. Write the label the fact-checker gave, not your own view (section 1). If the text is unclear, apply section 4.3 and say so in the note.
5. If you disagree with the fact-checker, write `disagree: <your label>, <one-line reason>` in the note.
6. Only compare with the answer key after you have finished.

### 6.1 Where the checked labels go

Save them as `data_validation/reference_labels.csv` with the columns `source_url`, `label`, `note` (the blind sheet's columns `url`, `YOUR_LABEL` also work). Leave a label empty if you have not checked that row yet. Allowed labels: `FALSE`, `MISLEADING`, `TRUE`, `UNVERIFIED`, `BOTH`, `NOT_A_FACTCHECK`.

Then run `python -m pipeline.rebuild` and the tests:
- **The reference-label test** compares the pipeline's own labels (without your corrections) to yours and needs at least 90% agreement on rows whose verdict was read from the text. Report this number.
- `python -m pipeline.agreement data_validation/reference_labels.csv` prints the agreement, Cohen's kappa and the confusion table.
- Your labels then **override** the pipeline: `label_source` becomes `hand_checked`, `BOTH` becomes MIXED, and `NOT_A_FACTCHECK` rows move to `data/excluded.csv`. Hand-checked FALSE/MISLEADING rows enter the main benchmark, including the former `stored` ones.

The file is keyed by `source_url`, which never changes.

---

## 7. Model inputs and the fields that give the answer away

| Field | Model input? | Why |
|---|---|---|
| `claim_text` | yes | The claim from the article (lead, quote, claim box). Verdict words removed |
| `evidence_text` | yes | The body without header, conclusion and verdict sentences |
| `headline` | **no** | Usually states the verdict ("... दाबी भ्रामक", "नझुक्किनुस्") |
| `conclusion_text` | **no** | It is the verdict |
| `label_source`, `annotator_notes` | **no** | Pipeline metadata |

When you annotate, you may read everything, including the headline and the conclusion.

---

## 8. Splits

- `split` is a time split by the earliest date in the claim group (train up to 2024, dev 2025, test 2026 onwards). `split_random` is a random split by claim group. Report both.
- Two articles about the same claim share a `claim_group_id`; a group is never split.
- The splits are provisional until they are frozen once with `python -m pipeline.splitter freeze` (after the full re-scrape). After that, never edit `data/splits_v2.0.csv`: a test checks its checksum. Rows added later get `new`.
