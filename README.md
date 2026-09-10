# NepFakeV2 🇳🇵

[![Daily Scrape](https://github.com/Nandansingh007/NepFakeV2/actions/workflows/daily_scrape.yml/badge.svg)](https://github.com/Nandansingh007/NepFakeV2/actions/workflows/daily_scrape.yml)
![Language](https://img.shields.io/badge/language-Nepali-red)
![License](https://img.shields.io/badge/license-CC%20BY%204.0-green)

---

## Description

NepFakeV2 is the first real, non-synthetic Nepali fact-checking dataset. It is built directly from verified fact-checks published by professional Nepali fact-checkers — not machine-translated, not LLM-generated.

All existing Nepali fake news datasets fail because they use either machine-translated US political content or LLM-generated text. NepFakeV2 breaks this cycle by sourcing directly from two active IFCN-adjacent Nepali fact-checkers.

The dataset is auto-updated daily.

---

## What It Does

NepFakeV2 provides a labeled dataset of Nepali fact-checked claims with three labels:

| Label | Name | Description |
|-------|------|-------------|
| 0 | REAL | Verified factual — confirmed by fact-checkers |
| 1 | FALSE/MISLEADING | Debunked — false or misleading content |
| 2 | UNVERIFIED | Cannot be confirmed or denied |

Data comes from two active Nepali fact-checking organizations:

| Source | Type | Language |
|--------|------|----------|
| [TechPana](https://techpana.com/factcheck/) | IFCN-certified fact-checker | Nepali |
| [NepalFactCheck](https://nepalfactcheck.org) | Non-profit fact-checker | Nepali |

Each example contains:

| Field | Description |
|-------|-------------|
| `example_id` | Unique ID — `NF2_YYYYMMDD_NNNN` |
| `claim_text` | Article headline (the claim) |
| `verdict_label` | 0 / 1 / 2 |
| `verdict_label_text` | REAL / FALSE_MISLEADING / UNVERIFIED |
| `evidence_text` | Full fact-check article body |
| `source_name` | techpana / nepalfactcheck |
| `source_url` | Original article URL |
| `date_published` | ISO date YYYY-MM-DD |
| `is_native_nepali` | True if Devanagari script detected |
| `topic_category` | politics / health / technology / society / environment / economy / other |
| `annotator_notes` | Edge case flags |

---

## How It Works

1. **Daily scrape** — GitHub Actions triggers every day at 9:15 AM NPT
2. **Incremental** — only articles published since the last run are fetched
3. **Stage 1** — TechPana and NepalFactCheck scraped and saved to `raw/`
4. **Stage 2** — raw data normalized: Bikram Sambat dates converted to ISO, raw Nepali verdict text mapped to labels 0/1/2, duplicates removed
5. **Auto-commit** — `data/nepfakev2.csv`, `data/nepfakev2.json` and `data/stats.json` committed to GitHub automatically after every run

---

<!-- STATS_START -->
## Dataset Statistics

**928 examples** &nbsp;|&nbsp; 2020-03-13 → 2026-09-10 &nbsp;|&nbsp; Updated: 2026-09-10 11:06 UTC

### Label Distribution

| Label | Count | % |
|-------|------:|--:|
| REAL                 |    61 |   6.6% |
| FALSE_MISLEADING     |   842 |  90.7% |
| UNVERIFIED           |    25 |   2.7% |
| UNKNOWN              |     0 |   0.0% |

### Source Breakdown

| Source | Examples | Verdict profile |
|--------|----------:|-----------------|
| TechPana         |  271 | भ्रामक: 73%  मिथ्या: 22%  अपुष्ट: 3%  unmapped: 2%  सही: 1%  ⚠ 5 unmapped |
| NepalFactCheck   |  662 | भ्रामक: 53%  मिथ्या: 35%  सही: 9%  अपुष्ट: 3% |

Nepali script coverage: **99.8%**
<!-- STATS_END -->

## Limitations

- **Label 0 is small** — fact-checkers rarely publish true verdicts by design. Researchers needing Label 0 balance can supplement using `scrapers/bbc_nepali.py`.
- **Cross-source duplicates** — the same claim may be fact-checked independently by both sources. Both records are retained as independent verifications.
- **claim_text is the article headline** — not an atomically extracted claim. Future versions will improve this.
- **TechPana requires Cloudflare Worker proxy** — TechPana blocks GitHub Actions datacenter IPs. See `.github/workflows/daily_scrape.yml` for proxy configuration.

---

## Citation

```bibtex
@dataset{singh2026nepfakev2,
  author    = {Singh, Nandan},
  title     = {NepFakeV2: A Live Benchmark Dataset for Nepali Misinformation Detection},
  year      = {2026},
  publisher = {GitHub},
  url       = {https://github.com/Nandansingh007/NepFakeV2},
  note      = {Version 1.0. Auto-updated daily.}
}
```

---

## License

- **Data** (`data/`): [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Code**: [MIT](LICENSE)

---

*Built by [Nandan Singh](https://github.com/Nandansingh007) · 2026*