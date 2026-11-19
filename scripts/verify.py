#!/usr/bin/env python3
"""Check an edition's facts against the pages it links to.

For every item in a data file, this opens the item's link and looks for the
version numbers, CVE identifiers, amounts and other figures used in the title
and summary. Anything it cannot find on the page is listed, along with links
that do not open and publication dates that disagree with the page.

It cannot judge meaning, so its output is a list of things to re-check by
hand, not a verdict. A figure can be right and still be listed (a count you
made yourself, a number the page writes in words).

Usage:
    python3 scripts/verify.py                 newest daily edition
    python3 scripts/verify.py 2026-11-19      a given edition
    python3 scripts/verify.py 2026-W47        a weekly digest (story updates and missed items)

Standard library only.
"""

import concurrent.futures
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import page as sws_page  # noqa: E402

SWS_ROOT = Path(__file__).resolve().parent.parent
SWS_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*"
SWS_FIGURE = re.compile(r"cve-\d{4}-\d{4,7}|\d[\d,]*(?:\.\d+)+|\d[\d,]*")


def sws_figures(text):
    """Version numbers, CVE ids and other figures in a piece of text, dates removed."""
    text = text.lower()
    text = re.sub(rf"\b\d{{1,2}}(?:st|nd|rd|th)? {SWS_MONTH}\b(?: \d{{4}})?", " ", text)
    text = re.sub(rf"\b{SWS_MONTH} \d{{1,2}}(?:st|nd|rd|th)?\b(?:,? \d{{4}})?", " ", text)
    found = []
    for figure in SWS_FIGURE.findall(text):
        figure = figure.rstrip(".,")
        if figure not in found and (len(figure) > 1 or figure.isdigit()):
            found.append(figure)
    return found


def sws_on_page(figure, haystack):
    """True when the figure appears on the page as a whole number or identifier."""
    plain = figure.replace(",", "")
    for candidate in {figure, plain}:
        if re.search(r"(?<![\d.])" + re.escape(candidate) + r"(?!\d|\.\d)", haystack):
            return True
    return False


def sws_page_date(parsed):
    """The publication date the page declares in its markup, if any."""
    for label, value, _ in parsed.dates + sws_page.sws_ld_dates(parsed.ld):
        if label == "published":
            match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
            if match:
                return dt.date(*map(int, match.groups()))
    return None


def sws_check_item(item):
    """Check one piece of text against its link. item: {"url", "text", "published" (optional)}."""
    notes = []
    try:
        final_url, status, content_type, markup = sws_page.sws_fetch(item["url"])
    except Exception as exc:
        return [f"could not open the link ({type(exc).__name__}: {str(exc)[:80]})"]
    if content_type in ("text/plain", "text/markdown", "application/json"):
        parsed, text = None, markup
    else:
        parsed, _, _ = sws_page.sws_parse(markup)
        everything = sws_page.SwsPageParser(skip_chrome=False)
        everything.feed(markup)
        text = everything.sws_text()[0] + " " + parsed.title + " " + " ".join(parsed.meta.values())
    if len(text) < 400:
        return [f"the link returned almost no text (HTTP {status}), so nothing could be checked"]
    haystack = text.lower().replace(",", "").replace("\xa0", " ")
    missing = [figure for figure in sws_figures(item["text"]) if not sws_on_page(figure, haystack)]
    if missing:
        notes.append("not found on the linked page: " + ", ".join(missing))
    declared = sws_page_date(parsed) if parsed else None
    try:
        published = dt.date.fromisoformat(item.get("published") or "")
    except ValueError:
        published = None
    if declared and published and abs((declared - published).days) > 1:
        notes.append(f"\"published\" is {published} but the page says {declared}")
    return notes


def sws_main():
    data_dir = SWS_ROOT / "data"
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target and "-W" in target:
        path = data_dir / "weekly" / f"{target}.json"
        digest = json.loads(path.read_text(encoding="utf-8"))
        items = [{"id": f"story: {story.get('id')}", "url": story.get("now_url", ""), "text": story.get("now", "")}
                 for story in digest.get("stories", [])]
        items += [{"id": f"missed: {missed.get('title', '')[:50]}", "url": missed.get("url", ""),
                   "text": missed.get("title", "") + " " + missed.get("summary", ""),
                   "published": missed.get("published")} for missed in digest.get("missed", [])]
        items += [{"id": f"coming up: {event.get('title', '')[:50]}", "url": event.get("url", ""),
                   "text": event.get("detail", "")} for event in digest.get("ahead", [])]
    else:
        if target:
            path = data_dir / f"{target}.json"
        else:
            files = sorted(data_dir.glob("20??-??-??.json"))
            if not files:
                sys.exit("No data files yet.")
            path = files[-1]
        day = json.loads(path.read_text(encoding="utf-8"))
        items = [{"id": item["id"], "url": item["url"], "text": item["title"] + " " + item["summary"],
                  "published": item.get("published")} for item in day.get("items", [])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(sws_check_item, items))
    flagged = 0
    print(f"Checking {len(items)} entries in {path.name} against their links\n")
    for item, notes in zip(items, results):
        if notes:
            flagged += 1
            print(f"RE-CHECK  {item['id']}")
            for note in notes:
                print(f"          {note}")
        else:
            print(f"ok        {item['id']}")
    print(f"\n{flagged} of {len(items)} entries to re-check by hand." if flagged
          else "\nEvery figure was found on its linked page.")


if __name__ == "__main__":
    sws_main()
