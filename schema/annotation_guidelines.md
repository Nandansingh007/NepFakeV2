# NepFakeV2 Annotation Guidelines

**Version:** 1.0
**Last updated:** September 2026

---

## Data Sources

Two active Nepali fact-checking organizations are used as data sources:

| Source | URL | Type | Language |
|--------|-----|------|----------|
| TechPana | [techpana.com/factcheck](https://techpana.com/factcheck/) | IFCN-certified fact-checker | Nepali |
| NepalFactCheck | [nepalfactcheck.org](https://nepalfactcheck.org) | Non-profit fact-checker | Nepali |

Both sources publish fact-checks with explicit verdict labels in Nepali. Only articles with a clear verdict are included in the dataset.

---

## Label Schema

NepFakeV2 uses three labels:

### Label 0 — REAL

A claim explicitly verified as factual by a professional fact-checker.

Raw verdicts that map to Label 0:

| Source | Raw verdict |
|--------|-------------|
| TechPana | सही |
| NepalFactCheck | सही सूचना |

---

### Label 1 — FALSE/MISLEADING

A claim debunked by a professional fact-checker as false, misleading, manipulated, or out of context.

Raw verdicts that map to Label 1:

| Source | Raw verdict |
|--------|-------------|
| TechPana | मिथ्या, भ्रामक, झुटो, गलत, भ्रम |
| NepalFactCheck | मिथ्या सूचना, भ्रामक सूचना |

---

### Label 2 — UNVERIFIED

A claim that cannot be confirmed or denied due to insufficient evidence at the time of fact-checking.

Raw verdicts that map to Label 2:

| Source | Raw verdict |
|--------|-------------|
| TechPana | अपुष्ट |
| NepalFactCheck | अपुष्ट सूचना |

---

### Label -1 — UNKNOWN

A claim where the verdict could not be extracted automatically by the label mapper.

This happens when:
- The article uses non-standard verdict vocabulary not in the label mapper
- The verdict section is missing or structured differently
- The scraper failed to extract the verdict text

Records with Label -1 are flagged in the dataset with `annotator_notes = "verdict_requires_manual_review"`. These records are included in the dataset but should be excluded or manually reviewed before use in model training.

The raw verdict text is preserved in `raw/` JSON files for manual inspection.

---

## Label Basis

All labels are assigned based on the verdict published by the fact-checker — not by editorial judgment or source credibility. The `label_basis` field in the dataset is always `fact_checker_verdict`.