---
license: cc-by-4.0
task_categories:
- text-classification
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
print(ds["train"][0])
```

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
| Labels | 3 (REAL, FALSE_MISLEADING, UNVERIFIED) |
| Sources | 2 (TechPana, NepalFactCheck) |
| Updates | Weekly — auto-synced from GitHub |
| Schema version | 1.0 |

## Labels

| Label | Int | Description |
|-------|-----|-------------|
| REAL | 0 | Verified factual — confirmed by fact-checkers |
| FALSE_MISLEADING | 1 | Debunked — false or misleading content |
| UNVERIFIED | 2 | Cannot be confirmed or denied |

> **On label imbalance:** 90%+ of examples are FALSE_MISLEADING. This reflects real-world distribution — fact-checkers publish mostly debunks by design. This is not a collection error.

## Data Sources

| Source | Type | Language | Coverage |
|--------|------|----------|----------|
| [TechPana](https://techpana.com/factcheck/) | IFCN-certified fact-checker | Nepali | Feb 2025 → present |
| [NepalFactCheck](https://nepalfactcheck.org) | Non-profit fact-checker (CMR-Nepal) | Nepali | Mar 2020 → present |

## Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `example_id` | string | Unique ID — `NF2_YYYYMMDD_NNNN` |
| `claim_text` | string | Article headline (the claim) |
| `verdict_label` | int | 0 / 1 / 2 |
| `verdict_label_text` | string | REAL / FALSE_MISLEADING / UNVERIFIED |
| `evidence_text` | string | Full fact-check article body |
| `source_name` | string | techpana / nepalfactcheck |
| `source_url` | string | Original article URL |
| `date_published` | string | ISO date YYYY-MM-DD |
| `is_native_nepali` | bool | True if Devanagari script detected |
| `topic_category` | string | politics / health / technology / society / environment / economy / other |
| `annotator_notes` | string | Edge case flags — empty if clean |
| `schema_version` | string | 1.0 |

## Dataset Statistics

See [stats.json](https://huggingface.co/datasets/Nandan007/NepFakeV2/resolve/main/data/stats.json) for live statistics updated after every pipeline run.

## Limitations

- **Label imbalance** — fact-checkers publish mostly debunks by design. 90%+ FALSE_MISLEADING reflects real-world distribution, not a collection error.
- **claim_text is the article headline** — not an atomically extracted claim. Future versions will improve atomic claim extraction.
- **Cross-source duplicates** — the same claim may be fact-checked by both sources independently. Both records are retained. Cross-source deduplication requires Nepali NER and is documented as future work.

## Citation

```bibtex
@dataset{singh2026nepfakev2,
  author    = {Singh, Nandan},
  title     = {NepFakeV2: A Live Benchmark Dataset for Nepali Misinformation Detection},
  year      = {2026},
  publisher = {Hugging Face},
  url       = {https://huggingface.co/datasets/Nandan007/NepFakeV2},
  note      = {Schema v1.0. Auto-updated weekly.}
}
```

## License

- **Data**: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Code**: [MIT](https://github.com/Nandansingh007/NepFakeV2/blob/main/LICENSE)

## Links

- GitHub: [github.com/Nandansingh007/NepFakeV2](https://github.com/Nandansingh007/NepFakeV2)
- Pipeline: see `scrapers/`, `pipeline/` in the GitHub repo