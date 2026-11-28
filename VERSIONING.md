# Versions, tags and how to cite NepFakeV2

NepFakeV2 is two things at once. It is a **live dataset** that grows every
week, and it is a **benchmark**, a frozen release that does not change.
They have different names. A score is only comparable when it names the
release.

## Three kinds of names

| Name | Example | What it is | Made by | Use it for |
|---|---|---|---|---|
| Release tag | `v2.0` | The benchmark: frozen splits plus the files in `data/v2.0/`. Never changes. | The maintainer, once | Reporting scores, citing |
| Run tag | `run-2026-11-30` | One weekly snapshot of the live data, on GitHub and on Hugging Face (same data on both) | The weekly workflow, after a successful push | Exact reproduction of an analysis on live data |
| Schema version | `2.0` (`schema_version` column) | The column layout | Code | Reading the files correctly |

The release tag and the schema version are separate. `v2.1` can add frozen
rows on schema 2.0.

## Live data or benchmark?

- **Live:** the `default` config on Hugging Face and `data/nepfakev2.csv` on
  `main`. New rows arrive every week and the provisional splits can move
  until the freeze. **Do not report benchmark scores on it.**
- **Benchmark v2.0** (after the release):

  ```python
  from datasets import load_dataset
  bench = load_dataset("Nandan007/NepFakeV2", "benchmark-v2.0", revision="v2.0")
  # bench["train"], bench["validation"], bench["test"]: main-benchmark rows, time split
  control = load_dataset("Nandan007/NepFakeV2", "benchmark-v2.0-random", revision="v2.0")
  ```

  The same files are in `data/v2.0/` at the git tag `v2.0`, with `SHA256SUMS`
  and `RELEASE.json` (date, counts, checksum of the split file).

## Reporting a score

- Name the release and the split: "NepFakeV2 v2.0, time test split".
- **Official metric:** macro-F1 over FALSE and MISLEADING on `test.csv`
  (time split). Also report `random_test.csv` and the majority baseline. The
  label balance moves a lot between years, so a time-split score alone mostly
  measures that shift.
- Score with `python -m pipeline.evaluate predictions.csv` (add `--random`
  for the control split). It refuses predictions that do not cover exactly
  the release rows, and it prints the release name next to the score.
- Cite the tag, not a download date (see the README's Citation section).

## Rows added after the freeze (`split = "new"`)

Rows scraped after the freeze get `split = split_random = "new"`. They are
never part of v2.0. You may split them however you like. Recommendations:

1. **Split by `claim_group_id`**, never row by row. One claim checked twice
   must not end up on both sides.
2. **If you train on v2.0, drop new rows whose `claim_group_id` also occurs
   in v2.0.** A new row about a claim that is already frozen keeps that
   group's ID, so this check finds repeats.
3. **Report the run tag you used** (for example `run-2027-03-01`) **and the
   `date_published` range** of the new rows, so that someone else can take
   exactly the same rows.
4. For a test of drift over time, train on v2.0 `train` and test on the new
   rows. Report it as an extra result, not as the v2.0 score.

## Release rule: when a new version comes out

- **Release files never change.** No release is edited after its tag. A
  fix goes into the next version. Between versions, known errors are listed
  in `CHANGELOG.md` under "Errata for vX.Y".
- **Major (v3.0):** a change that breaks users. A column is renamed or
  removed, the ID format changes, or a label definition changes.
- **Minor (v2.1):** the same schema, with new frozen rows from the `new`
  pool or hand-checked label corrections. v2.0 rows keep their splits. v2.1
  gets a new folder (`data/v2.1/`) and a new tag.
- **When a minor release is cut (default, to be confirmed by the maintainer):**
  whichever comes first of
  - at least 200 new main-benchmark rows since the last release,
  - 12 months since the last release with at least 50 new benchmark rows,
  - hand-checked corrections that change at least 1% of the labels in a
    frozen test split.
- **Every release has:** a `CHANGELOG.md` entry, `RELEASE.json`,
  `SHA256SUMS`, the same tag on git and on Hugging Face, and
  `CITATION.cff` with the release version and date.
- Note: the code for a v2.1 freeze (freezing the `new` rows while keeping
  every v2.0 split) is not built yet. It is a small change, to make before
  the first minor release.

## How to cut a release (maintainer, PowerShell)

1. Freeze and write the release files. Do this once, after the full
   re-scrape and the hand check:

   ```powershell
   python -m pipeline.splitter freeze
   python -m pipeline.rebuild
   python -m pytest -q
   python -m pipeline.splitter release   # writes data/v2.0/, card configs, CITATION.cff date
   git add -A data README_HF.md CITATION.cff
   git commit -m "release v2.0"
   git push
   ```

2. Push to the Hub. Go to Actions, open "NepFakeV2 Data Pipeline" and click
   "Run workflow" (leave `full_rescrape` unticked). Wait until it is green.
   It uploads `data/v2.0/` and the card with the `benchmark-v2.0` configs.

3. Tag both sides on the same data:

   ```powershell
   git pull
   git tag -a v2.0 -m "NepFakeV2 v2.0 benchmark release"
   git push origin v2.0
   $env:HF_TOKEN = Read-Host "Hugging Face write token"   # not saved anywhere
   python -m pipeline.versioning release-tag              # checks the Hub has the same SHA256SUMS, then tags
   Remove-Item Env:HF_TOKEN
   ```

   `release-tag` refuses to run if the Hub does not have the release files
   yet, if they differ from yours, or if `v2.0` already exists there.
