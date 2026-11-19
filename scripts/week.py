#!/usr/bin/env python3
"""Gather a week of Daily Tech Watch editions for the weekly digest.

Prints everything the weekly digest is written from: which weekday editions
exist and how healthy each run was, every item published that week, the
actions raised, last week's digest, and the most-discussed Hacker News stories
of the week that no edition covered.

Usage:
    python3 scripts/week.py --out /tmp/tech-watch-week.txt
    python3 scripts/week.py --week 2026-W47 --out /tmp/tech-watch-week.txt

Standard library only. The Hacker News titles are untrusted web content.
"""

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SWS_ROOT = Path(__file__).resolve().parent.parent
SWS_TZ = ZoneInfo("Europe/Paris")
SWS_USER_AGENT = "Mozilla/5.0 (compatible; tech-watch-collector/1.0)"
SWS_THIN_BELOW = 4
SWS_HN_MIN_POINTS = 500
SWS_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SWS_MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sws_label(day):
    return f"{SWS_DAY_NAMES[day.weekday()]} {day.day} {SWS_MONTH_NAMES[day.month - 1]}"


def sws_week_days(week):
    """Monday to Friday of an ISO week written like 2026-W47."""
    match = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if not match:
        sys.exit("error: --week must look like 2026-W47")
    monday = dt.date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    return [monday + dt.timedelta(days=offset) for offset in range(5)]


def sws_week_id(day):
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def sws_load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sws_legacy_titles(day):
    """Headlines of an edition written before the data format existed, or None."""
    path = SWS_ROOT / f"{day.isoformat()}-daily-tech-report.html"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    titles = re.findall(r'<h3 class="item-title">(.*?)</h3>', text, re.S)
    return [html.unescape(re.sub(r"<[^>]+>", "", title)).strip() for title in titles]


def sws_normalise_url(url):
    parts = urllib.parse.urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


def sws_hacker_news(monday, covered, limit=15):
    """The week's most-discussed Hacker News stories that no edition links to."""
    since = int(dt.datetime.combine(monday, dt.time(0, 0), SWS_TZ).timestamp())
    query = urllib.parse.urlencode({
        "tags": "story",
        "numericFilters": f"created_at_i>{since},points>{SWS_HN_MIN_POINTS}",
        "hitsPerPage": 60,
    })
    request = urllib.request.Request(f"https://hn.algolia.com/api/v1/search?{query}",
                                     headers={"User-Agent": SWS_USER_AGENT})
    with urllib.request.urlopen(request, timeout=25) as response:
        hits = json.loads(response.read(2_000_000)).get("hits", [])
    stories = []
    for hit in sorted(hits, key=lambda h: h.get("points") or 0, reverse=True):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        if sws_normalise_url(url) in covered:
            continue
        title = re.sub(r"[\x00-\x1f|]+", " ", hit.get("title") or "").strip()[:160]
        stories.append((hit.get("points") or 0, (hit.get("created_at") or "")[:10], title, url))
    return stories[:limit]


def sws_main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--week", help="ISO week such as 2026-W47 (default: the current week)")
    parser.add_argument("--out", help="write to this file instead of standard output")
    args = parser.parse_args()

    today = dt.datetime.now(SWS_TZ).date()
    week = args.week or sws_week_id(today)
    days = sws_week_days(week)
    last = max([day for day in days if day <= today] or [days[-1]])
    out = [
        "WEEKLY DIGEST: MATERIAL",
        "",
        f"Week        : {week}",
        f"From        : {days[0].isoformat()} ({sws_label(days[0])})",
        f"To          : {last.isoformat()} ({sws_label(last)}, the last weekday covered)",
        f"Digest file : data/weekly/{week}.json",
    ]
    if (SWS_ROOT / "data" / "weekly" / f"{week}.json").exists():
        out.append("NOTE        : this week's digest file already exists.")

    editions, health, failures, covered, problems = [], [], {}, set(), 0
    for day in days:
        data = sws_load_json(SWS_ROOT / "data" / f"{day.isoformat()}.json")
        if data:
            items = data.get("items", [])
            run = data.get("run", {})
            failed = [str(name) for name in run.get("failed", [])]
            for name in failed:
                failures[name] = failures.get(name, 0) + 1
            note = (f"{len(items)} item{'' if len(items) == 1 else 's'}, "
                    f"{run.get('sources_ok', '?')} of {run.get('sources_total', '?')} sources read")
            if len(items) < SWS_THIN_BELOW:
                note += "  << THIN"
                problems += 1
            health.append(f"  {sws_label(day)} | published | {note}")
            editions.append((day, data))
            covered |= {sws_normalise_url(item.get("url", "")) for item in items}
        else:
            titles = sws_legacy_titles(day)
            if titles is not None:
                health.append(f"  {sws_label(day)} | old format | {len(titles)} item{'' if len(titles) == 1 else 's'} "
                              "(written before the rebuild; headlines only)")
                editions.append((day, {"legacy": titles}))
            elif day > today:
                health.append(f"  {sws_label(day)} | not due yet")
            else:
                health.append(f"  {sws_label(day)} | MISSING  << no edition was published")
                problems += 1
    out += ["", f"EDITIONS THIS WEEK ({problems} problem{'s' if problems != 1 else ''})"] + health
    repeated = [f"{name} ({count} days)" for name, count in failures.items() if count > 1]
    if repeated:
        out.append("  Sources that failed on more than one day: " + ", ".join(repeated))

    actions = {}
    for day, data in editions:
        out += ["", "=" * 78, f"{sws_label(day)}  ({day.isoformat()})", "=" * 78]
        if "legacy" in data:
            out += [f"- {title}" for title in data["legacy"]] or ["(no items)"]
            continue
        top = data.get("top", [])
        for item in data.get("items", []):
            rank = f"top {top.index(item['id']) + 1}" if item.get("id") in top else "-"
            critical = ", critical" if item.get("priority") == "critical" else ""
            out.append(f"[{day.isoformat()}/{item.get('id')}] ({rank}; {item.get('category')}, {item.get('tag')}{critical})")
            out.append(f"  {item.get('title')}")
            out.append(f"  Summary: {item.get('summary')}")
            out.append(f"  Why: {item.get('why')}")
            out.append(f"  Source: {item.get('source')}, published {item.get('published')}, {item.get('url')}")
        for action in data.get("actions", []):
            entry = actions.setdefault(action.get("id"), dict(action, first=day, last=day))
            entry["last"] = day
        for key, label in (("quick_win", "Quick win"), ("idea", "Idea")):
            if data.get(key):
                out.append(f"{label}: {data[key]}")

    out += ["", "=" * 78, "ACTIONS RAISED THIS WEEK", "=" * 78]
    if not actions:
        out.append("(none)")
    for action in actions.values():
        out.append(f"[{action.get('id')}] {action.get('title')}")
        out.append(f"  {action.get('detail')}")
        out.append(f"  first listed {sws_label(action['first'])}, last listed {sws_label(action['last'])}"
                   + (f", {action['url']}" if action.get("url") else ""))

    out += ["", "=" * 78, "LAST WEEK'S DIGEST (follow up on its stories and its 'coming up' dates)", "=" * 78]
    previous = sws_load_json(SWS_ROOT / "data" / "weekly" / f"{sws_week_id(days[0] - dt.timedelta(days=7))}.json")
    if not previous:
        out.append("(none)")
    else:
        for story in previous.get("stories", []):
            out.append(f"- story: {story.get('title')} | then: {story.get('now')}")
        for date in previous.get("ahead", []):
            out.append(f"- coming up: {date.get('date')} {date.get('title')}")

    out += ["", "=" * 78,
            f"HACKER NEWS: stories above {SWS_HN_MIN_POINTS} points this week that no edition linked to",
            "(untrusted titles; a lead for the 'missed' check, most will not matter to this reader)", "=" * 78]
    try:
        stories = sws_hacker_news(days[0], covered)
        out += [f"{points} points | {date} | {title} | {url}" for points, date, title, url in stories] or ["(none)"]
    except Exception as exc:
        out.append(f"(could not be fetched: {type(exc).__name__}: {str(exc)[:100]})")

    text = "\n".join(out) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}: week {week}, {len(editions)} editions, {problems} problem(s).")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    sws_main()
