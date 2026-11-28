"""
Test: what the 28 Nov 2026 full re-scrape showed (see CHANGELOG 2.0).

  1. TechPana pages cut short: 10 of 275 pages ended right after a
     "हेर्नुहोस् … स्क्रिनशट" link block, at a different point in each scrape of
     the same article (incomplete HTML). The scraper now fetches such a page
     again and records page_complete.
  2. The og:image URL the badge comes from is stored (badge_url), so a badge
     that changes between scrapes can be shown.
  3. Rows whose label no rule read from the text go to a hand-check sheet.
"""
import json

import pytest

# Last lines of real body_text from the 28 Nov 2026 scrape (2026/155084):
# the cut copy ends at the link block, the full copy runs to the sidebar.
CUT_TAIL = ("उक्त पोस्टमा यो सामाग्री तयार पार्दा सम्म ३२ हजारभन्दा धेरै रियाक्सन ७८ सय बढी "
            "कमेन्ट र ११ सय बढी शेयर भएको छ । हेर्नुहोस्\nपोस्ट\n,\nअर्काइभ लिङ्क\nतथा स्क्रिनशट ।")
FULL_TAIL = ("निष्कर्ष\nभाइरल तस्बिरहरू एआई निर्मित हुन् । दाबी भ्रामक हो ।\n"
             "पछिल्ला अपडेट")


def _html(text, og="https://techpana.com/uploads/Misleading_badge.jpg"):
    paragraphs = "".join(f"<p>{line}</p>" for line in text.split("\n") if line)
    return ("<html><head>"
            f'<meta property="og:image" content="{og}">'
            "</head><body><h1>फ्याक्टचेक: भाइरल तस्बिर</h1>"
            f'<div class="article-content">{paragraphs}</div></body></html>')


LEAD = ("माघ ८, २०८२ १०:३२\nसामाजिक सञ्जालमा बालेन शाहलाई धम्की दिने व्यक्ति पक्राउ परेको "
        "दाबीसहित तस्बिर भाइरल भएको छ ।\nदाबी\n")


def test_cut_page_is_recognised():
    from scrapers.techpana import page_reaches_end
    assert not page_reaches_end(LEAD + CUT_TAIL)
    assert page_reaches_end(LEAD + CUT_TAIL + "\n" + FULL_TAIL)


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_cut_page_is_fetched_again_and_the_full_copy_kept(monkeypatch):
    from scrapers.techpana import TechpanaScraper
    scraper = TechpanaScraper()
    pages = [_html(LEAD + CUT_TAIL), _html(LEAD + CUT_TAIL + "\n" + FULL_TAIL)]
    calls = []
    monkeypatch.setattr(scraper, "fetch_page", lambda url: calls.append(url) or pages[len(calls) - 1])
    article = scraper.scrape_article("https://techpana.com/2026/155084/slug")
    assert len(calls) == 2
    assert article.page_complete is True
    assert "पछिल्ला अपडेट" in article.body_text
    assert article.raw_verdict_text == "भ्रामक"            # from the conclusion, not cut away


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_page_still_cut_after_retries_is_marked(monkeypatch):
    from scrapers.techpana import PAGE_RETRIES, TechpanaScraper
    scraper = TechpanaScraper()
    calls = []
    monkeypatch.setattr(scraper, "fetch_page", lambda url: calls.append(url) or _html(LEAD + CUT_TAIL))
    article = scraper.scrape_article("https://techpana.com/2026/155084/slug")
    assert len(calls) == 1 + PAGE_RETRIES
    assert article.page_complete is False


@pytest.mark.filterwarnings("ignore:A test tried to use socket")
def test_badge_url_is_stored(monkeypatch, tmp_path):
    from scrapers.techpana import TechpanaScraper
    scraper = TechpanaScraper()
    og = "https://techpana.com/uploads/2026/01/Misleading_badge.jpg"
    monkeypatch.setattr(scraper, "fetch_page",
                        lambda url: _html(LEAD + CUT_TAIL + "\n" + FULL_TAIL, og=og))
    article = scraper.scrape_article("https://techpana.com/2026/155084/slug")
    assert article.badge_url == og
    monkeypatch.setattr(scraper, "raw_dir", tmp_path)
    record = json.loads(scraper.save_raw([article]).read_text(encoding="utf-8"))[0]
    assert record["badge_url"] == og and record["page_complete"] is True


def test_label_sheet_lists_rows_no_rule_could_read(tmp_path, monkeypatch):
    from pipeline import normalizer, reference_labels
    tp = tmp_path / "techpana"
    tp.mkdir()
    base = {"source_name": "techpana", "date_published": "माघ ८, २०८२ १०:३२",
            "title": "फ्याक्टचेक: बालेनलाई धम्की दिने पक्राउ परेको दाबी"}
    body_badge_only = LEAD + "क्याप्सनमा ‘बालेन शाहलाई गोली ठोक्छु भन्ने व्यक्ति पक्राउ परेको छ भन्दै’ लेखिएको छ ।\nनिष्कर्ष\nतस्बिर एआई निर्मित हो ।\n"
    rows = [
        dict(base, source_url="https://techpana.com/2026/1/badge", body_text=body_badge_only,
             raw_verdict_text="भ्रामक", badge_url="https://techpana.com/x/Misleading.jpg"),
        dict(base, source_url="https://techpana.com/2026/2/none", body_text=body_badge_only,
             raw_verdict_text=""),
        dict(base, source_url="https://techpana.com/2026/3/fine",
             body_text=LEAD + "निष्कर्ष\nदाबी भ्रामक हो ।\n", raw_verdict_text="भ्रामक"),
    ]
    (tp / "2026-11-28.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(normalizer, "RAW_DIRS", {"techpana": tp})
    monkeypatch.setattr(reference_labels, "REFERENCE_FILE", tmp_path / "none.csv")
    out = tmp_path / "labels_to_check.csv"
    assert reference_labels.write_label_sheet(out) == 2
    import csv
    got = {r["source_url"]: r for r in csv.DictReader(open(out, encoding="utf-8-sig"))}
    assert got["https://techpana.com/2026/1/badge"]["label_source"] == "stored"
    assert got["https://techpana.com/2026/1/badge"]["badge_url"].endswith("Misleading.jpg")
    assert got["https://techpana.com/2026/2/none"]["label_source"] == "none"
    assert all(r["label"] == "" for r in got.values())


@pytest.mark.data
def test_few_techpana_pages_cut_short():
    # Only files written since the check exists carry page_complete.
    import warnings
    from utils.helpers import snapshot_files
    records = [r for f, _ in snapshot_files("raw/techpana")
               for r in json.loads(f.read_text(encoding="utf-8")) if "page_complete" in r]
    if not records:
        pytest.skip("no raw file written with the page check yet")
    cut = [r["source_url"] for r in records if r["page_complete"] is False]
    if cut:
        warnings.warn(f"techpana: {len(cut)} pages still cut short after retries: {cut[:5]}")
    assert len(cut) <= max(5, 0.05 * len(records)), cut[:10]


@pytest.mark.parametrize("args, expected", [
    (("FALSE", "conclusion", "ne", None), ""),
    (("MISLEADING", "nfc_header", "ne", True), ""),
    (("TRUE", "nfc_header", "ne", None), "label_TRUE"),
    (("FALSE", "stored", "en", None), "label_source_stored|language_en"),
    (("MISLEADING", "conclusion_mixed", "ne", None), ""),      # in the benchmark since 28 Nov 2026
    (("FALSE", "conclusion", "ne", False), "page_cut"),
])
def test_benchmark_reasons(args, expected):
    from pipeline.normalizer import benchmark_reasons
    assert benchmark_reasons(*args) == expected


def test_cut_page_is_kept_but_left_out_of_the_benchmark():
    from pipeline.normalizer import normalize_article
    body = LEAD + CUT_TAIL + "\nनिष्कर्ष\nदाबी भ्रामक हो ।\n"
    raw = {"source_name": "techpana", "source_url": "https://techpana.com/2026/155084/slug",
           "title": "फ्याक्टचेक: बालेनलाई धम्की दिने पक्राउ परेको दाबी", "body_text": body,
           "raw_verdict_text": "भ्रामक", "date_published": "माघ ८, २०८२ १०:३२",
           "date_scraped": "2026-11-28"}
    full = normalize_article(dict(raw, page_complete=True), {})
    cut = normalize_article(dict(raw, page_complete=False), {})
    assert full.in_main_benchmark and full.benchmark_exclusion_reason == ""
    assert not cut.in_main_benchmark and cut.benchmark_exclusion_reason == "page_cut"
