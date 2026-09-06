# Contributing to NepFakeV2

Thank you for your interest in contributing to NepFakeV2.

---

## Ways to Contribute

### 1. Report a labeling error
If you find an article that is incorrectly labeled, open a GitHub Issue with:
- The `example_id` of the record
- The current label
- What the correct label should be
- Your reasoning

### 2. Add a new source
If you know of an active Nepali fact-checker not currently in the dataset:
- Open a GitHub Issue describing the source
- Include the URL, methodology page, and label vocabulary
- We will evaluate and add it if it meets the criteria

**Source inclusion criteria:**
- Must be an active Nepali fact-checking organization
- Must have a documented verification methodology
- Must publish verdicts in a consistent, scrapeable format
- Must not have restricted scraping (robots.txt or owner request)

### 3. Improve scraper code
If a scraper breaks due to website changes:
- Open a Pull Request with the fix
- Include a test showing the scraper works

### 4. Improve normalization
If you find verdict keywords not being mapped correctly:
- Open a Pull Request updating `pipeline/label_mapper.py`
- Include examples of the unmapped verdicts

---

## What We Do Not Accept

- Synthetic or LLM-generated examples
- Machine-translated content
- Examples from sources without a documented verification methodology
- Labels assigned by source credibility alone without fact-checker verification

---

## Development Setup

```bash
git clone https://github.com/Nandansingh007/NepFakeV2.git
cd NepFakeV2
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate
pip install -r requirements.txt
```

Run the full pipeline locally:

```bash
python -m pipeline.collector
```

---

## Contact

Open a GitHub Issue for any questions or suggestions.

---

*Nandan Singh · 2026*