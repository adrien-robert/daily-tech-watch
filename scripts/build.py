#!/usr/bin/env python3
"""Validate data/*.json and render the Daily Tech Watch site.

Each data/YYYY-MM-DD.json file is one day's report. This script checks every
file, then writes:

    YYYY-MM-DD-daily-tech-report.html   one page per data file
    index.html                          a copy of the newest report
    YYYY-Www-weekly-digest.html         one page per data/weekly/YYYY-Www.json file
    archive.html                        every report, old and new, with search

Reports published before the data format existed stay as they are; they are
only listed in the archive.

Usage:
    python3 scripts/build.py            validate and render
    python3 scripts/build.py --check    validate only

Standard library only. Text fields are plain text: everything is HTML-escaped,
and `backticks` become <code>.
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SWS_ROOT = Path(__file__).resolve().parent.parent
SWS_TZ = ZoneInfo("Europe/Paris")
SWS_REPORT_FILE = "{date}-daily-tech-report.html"
SWS_REPORT_GLOB = "20??-??-??-daily-tech-report.html"
SWS_WEEKLY_FILE = "{week}-weekly-digest.html"
SWS_WEEK_ID = re.compile(r"^(\d{4})-W(\d{2})$")
SWS_NOINDEX = '<meta name="robots" content="noindex, nofollow">'
SWS_TAGS = {
    "security": "🔒 Security",
    "breaking": "⚠️ Breaking",
    "deadline": "⏰ Deadline",
    "important": "❗ Important",
    "new": "🆕 New",
    "update": "🔄 Update",
    "milestone": "🎯 Milestone",
    "tool": "🔧 Tool",
    "trend": "📈 Trend",
    "tutorial": "📚 Tutorial",
}
SWS_MAX_ITEMS = 14
SWS_THIN_BELOW = 4
SWS_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SWS_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
SWS_PLACEHOLDER = re.compile(r"^(no (verifiable|verified|new)\b|quiet (news )?day)", re.I)
SWS_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
SWS_HEDGE = re.compile(
    r"could(?: not|n[’']t) (?:be )?(?:confirm|verif|reach)|not (?:independently )?(?:confirmed|verified)"
    r"|unverified|unable to (?:confirm|verify)", re.I)


# ── Loading ──────────────────────────────────────────────────────────────

def sws_load_categories():
    config = json.loads((SWS_ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
    return config["categories"]


def sws_load_days(data_dir, errors):
    """Read every data file. Returns {date: data} in date order."""
    days = {}
    for path in sorted(data_dir.glob("20??-??-??.json")):
        try:
            days[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{path.name}: not valid JSON ({exc})")
    return days


def sws_parse_datetime(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def sws_parse_day(value):
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


# ── Validation ───────────────────────────────────────────────────────────

def sws_check_text(obj, key, where, errors, low=1, high=None, required=True):
    value = obj.get(key)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{where}: \"{key}\" is missing or empty")
        return
    length = len(value.strip())
    if length < low:
        errors.append(f"{where}: \"{key}\" is too short ({length} characters, minimum {low})")
    if high and length > high:
        errors.append(f"{where}: \"{key}\" is too long ({length} characters, maximum {high})")


def sws_check_url(value, where, errors):
    parts = urlsplit(value) if isinstance(value, str) else None
    if not parts or parts.scheme not in ("http", "https") or "." not in parts.netloc:
        errors.append(f"{where}: \"url\" must be a full http(s) link, got {value!r}")
        return False
    return True


def sws_validate_day(date, day, categories, earlier_urls):
    """Check one day's data. Returns (errors, warnings) as lists of strings."""
    errors, warnings = [], []
    name = f"{date}.json"
    if not isinstance(day, dict):
        return [f"{name}: the file must contain a JSON object"], warnings
    if day.get("date") != date:
        errors.append(f"{name}: \"date\" must be {date!r} to match the file name")

    window = day.get("window") if isinstance(day.get("window"), dict) else {}
    start, end = sws_parse_datetime(window.get("from")), sws_parse_datetime(window.get("to"))
    if not start or not end:
        errors.append(f"{name}: \"window.from\" and \"window.to\" must be ISO date-times with an offset, "
                      "copied from the collector output")
    elif start >= end:
        errors.append(f"{name}: \"window.from\" must be earlier than \"window.to\"")

    items = day.get("items")
    if not isinstance(items, list):
        errors.append(f"{name}: \"items\" must be a list (it may be empty)")
        items = []
    if len(items) > SWS_MAX_ITEMS:
        errors.append(f"{name}: {len(items)} items, maximum {SWS_MAX_ITEMS}. Keep the ones that matter most")
    report_day = sws_parse_day(date)
    ids, urls = set(), set()
    for number, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errors.append(f"{name}: items[{number}] must be an object")
            continue
        where = f"{name}: item {number} ({item.get('id', 'no id')})"
        item_id = item.get("id")
        if not isinstance(item_id, str) or not SWS_ID.match(item_id):
            errors.append(f"{where}: \"id\" must be a short slug such as \"wordpress-7-2-beta\"")
        elif item_id in ids:
            errors.append(f"{where}: duplicate \"id\"")
        ids.add(item_id)
        if item.get("category") not in categories:
            errors.append(f"{where}: \"category\" must be one of {', '.join(categories)}")
        if item.get("tag") not in SWS_TAGS:
            errors.append(f"{where}: \"tag\" must be one of {', '.join(SWS_TAGS)}")
        if item.get("priority") not in (None, "critical"):
            errors.append(f"{where}: \"priority\" must be \"critical\" or left out")
        if item.get("verified") not in ("feed", "page"):
            errors.append(f"{where}: \"verified\" must be \"feed\" (date taken from a feed entry) "
                          "or \"page\" (date read on the opened page)")
        sws_check_text(item, "title", where, errors, 10, 110)
        sws_check_text(item, "summary", where, errors, 40, 700)
        sws_check_text(item, "why", where, errors, 20, 450)
        sws_check_text(item, "source", where, errors, 2, 60)
        sws_check_text(item, "resurfaced", where, errors, 10, 200, required=False)
        if sws_check_url(item.get("url"), where, errors):
            if item["url"] in urls:
                errors.append(f"{where}: the same \"url\" is used by another item today")
            urls.add(item["url"])
            if item["url"] in earlier_urls:
                warnings.append(f"{where}: this link was already used on {earlier_urls[item['url']]}. "
                                "Keep it only if something new happened, and say what")
            if urlsplit(item["url"]).path.strip("/") == "":
                warnings.append(f"{where}: the link is a home page. Link to the specific article or release")
        published = sws_parse_day(item.get("published"))
        if not published:
            errors.append(f"{where}: \"published\" must be a date like 2026-11-19")
        elif report_day and published > report_day:
            errors.append(f"{where}: \"published\" ({published}) is after the report date")
        elif start and published < start.astimezone(SWS_TZ).date() - dt.timedelta(days=1) \
                and not item.get("resurfaced"):
            errors.append(f"{where}: published {published}, before this report's window. Drop it, or add "
                          "\"resurfaced\" with one sentence on why it matters today")
        for key in ("title", "summary", "why"):
            if isinstance(item.get(key), str) and SWS_HEDGE.search(item[key]):
                warnings.append(f"{where}: \"{key}\" hedges about something unconfirmed. "
                                "Leave out what you could not confirm instead of flagging it")

    top = day.get("top")
    wanted = min(3, len(items))
    if not isinstance(top, list) or len(top) != wanted or len(set(top)) != len(top) \
            or any(entry not in ids for entry in top):
        errors.append(f"{name}: \"top\" must list the ids of the {wanted} most important items, in order")

    actions = day.get("actions", [])
    if not isinstance(actions, list):
        errors.append(f"{name}: \"actions\" must be a list (it may be empty)")
        actions = []
    for number, action in enumerate(actions, 1):
        if not isinstance(action, dict):
            errors.append(f"{name}: actions[{number}] must be an object")
            continue
        where = f"{name}: action {number} ({action.get('id', 'no id')})"
        if not isinstance(action.get("id"), str) or not SWS_ID.match(action["id"]):
            errors.append(f"{where}: \"id\" must be a short slug")
        sws_check_text(action, "title", where, errors, 8, 110)
        sws_check_text(action, "detail", where, errors, 20, 500)
        if action.get("status") not in ("new", "open"):
            errors.append(f"{where}: \"status\" must be \"new\" (raised today) or \"open\" (carried over)")
        if not sws_parse_day(action.get("opened")):
            errors.append(f"{where}: \"opened\" must be the date the action first appeared")
        if action.get("due") is not None and not sws_parse_day(action.get("due")):
            errors.append(f"{where}: \"due\" must be a date or left out")
        if action.get("url") is not None:
            sws_check_url(action.get("url"), where, errors)

    for key in ("quick_win", "idea"):
        sws_check_text(day, key, name, errors, 30, 800, required=False)

    run = day.get("run")
    if not isinstance(run, dict):
        errors.append(f"{name}: \"run\" is missing (sources_ok, sources_total, failed, searches, pages_opened)")
    else:
        for key in ("sources_ok", "sources_total", "searches", "pages_opened"):
            if not isinstance(run.get(key), int) or run[key] < 0:
                errors.append(f"{name}: \"run.{key}\" must be a whole number")
        if not isinstance(run.get("failed"), list):
            errors.append(f"{name}: \"run.failed\" must be a list of source names (it may be empty)")

    if not errors and len(items) < SWS_THIN_BELOW:
        warnings.append(f"{name}: only {len(items)} items. Say so at the top of your final message")
    return errors, warnings


# ── Formatting helpers ───────────────────────────────────────────────────

def sws_inline(text):
    """Escape plain text and turn `backticks` into <code>."""
    escaped = html.escape(text.strip(), quote=True)
    return re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)


def sws_long_date(day):
    return f"{SWS_WEEKDAYS[day.weekday()]} {day.day} {SWS_MONTHS[day.month - 1]} {day.year}"


def sws_short_date(day):
    return f"{SWS_WEEKDAYS[day.weekday()][:3]} {day.day} {SWS_MONTHS[day.month - 1][:3]}"


def sws_plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def sws_fill(template, values):
    """Replace {{tokens}} in one pass, so inserted text is never re-scanned."""
    return re.sub(r"\{\{([a-z_]+)\}\}", lambda match: values[match.group(1)], template)


def sws_asset_version():
    digest = hashlib.sha1()
    for path in sorted((SWS_ROOT / "assets").glob("*")):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:8]


def sws_external_link(url, label, css_class=""):
    attr = f' class="{css_class}"' if css_class else ""
    return f'<a{attr} href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{label}</a>'


# ── Report rendering ─────────────────────────────────────────────────────

def sws_render_item(item):
    classes = "item"
    if item.get("priority") == "critical":
        classes += " is-critical"
    elif item["tag"] == "security":
        classes += " is-security"
    published = dt.date.fromisoformat(item["published"])
    source = sws_external_link(item["url"], "via " + html.escape(item["source"].strip()), "item-source")
    return f"""                <article class="{classes}" id="item-{item['id']}" data-tag="{item['tag']}">
                    <div class="item-header">
                        <h3 class="item-title">{sws_external_link(item['url'], sws_inline(item['title']))}</h3>
                        <span class="item-tag" data-tag="{item['tag']}">{SWS_TAGS[item['tag']]}</span>
                    </div>
                    <p class="item-summary">{sws_inline(item['summary'])}</p>
                    <p class="item-why"><strong>Why it matters:</strong> {sws_inline(item['why'])}</p>
                    <p class="item-meta">{source} · published <time datetime="{published}">{sws_short_date(published)}</time></p>
                </article>"""


def sws_render_top(day, categories):
    by_id = {item["id"]: item for item in day["items"]}
    if not day["top"]:
        return ""
    rows = "\n".join(
        f"""                <li><a href="#item-{item_id}">{sws_inline(by_id[item_id]['title'])}</a>"""
        f"""<span class="top-cat">{html.escape(categories[by_id[item_id]['category']])}</span></li>"""
        for item_id in day["top"])
    return f"""        <section class="panel" aria-labelledby="topTitle">
            <h2 class="panel-title" id="topTitle">Top stories</h2>
            <ol class="top-list">
{rows}
            </ol>
        </section>"""


def sws_render_actions(day):
    actions = day.get("actions") or []
    if not actions:
        return """        <section class="panel panel-actions is-clear" aria-labelledby="actionsTitle">
            <h2 class="panel-title" id="actionsTitle">To do</h2>
            <p>Nothing needs action today.</p>
        </section>"""
    rows = []
    for action in actions:
        opened = dt.date.fromisoformat(action["opened"])
        meta = ["Raised today" if action["status"] == "new" else f"Open since {sws_short_date(opened)}"]
        if action.get("due"):
            meta.append(f"due {sws_short_date(dt.date.fromisoformat(action['due']))}")
        if action.get("url"):
            meta.append(sws_external_link(action["url"], "details"))
        badge = '<span class="badge">New</span>' if action["status"] == "new" else ""
        rows.append(f"""                <li>
                    <div class="action-title">{sws_inline(action['title'])}{badge}</div>
                    <p class="action-detail">{sws_inline(action['detail'])}</p>
                    <p class="action-meta">{' · '.join(meta)}</p>
                </li>""")
    return f"""        <section class="panel panel-actions" aria-labelledby="actionsTitle">
            <h2 class="panel-title" id="actionsTitle">To do</h2>
            <ul class="action-list">
{chr(10).join(rows)}
            </ul>
        </section>"""


def sws_render_categories(day, categories):
    if not day["items"]:
        return """        <section class="empty-state">
            <h2>Nothing worth your time today</h2>
            <p>The sources were checked and nothing new in this window made the cut.</p>
        </section>"""
    blocks = []
    for key, label in categories.items():
        items = [item for item in day["items"] if item["category"] == key]
        if not items:
            continue
        cards = "\n".join(sws_render_item(item) for item in items)
        blocks.append(f"""        <details class="category" open>
            <summary class="category-header">
                <h2>{html.escape(label)}</h2>
                <span class="category-count">{sws_plural(len(items), 'item')}</span>
            </summary>
            <div class="items-list">
{cards}
            </div>
        </details>""")
    return "\n\n".join(blocks)


def sws_render_closing(day):
    boxes = []
    for key, css, label in (("quick_win", "is-quickwin", "✨ Quick win"), ("idea", "is-idea", "💡 Idea")):
        if day.get(key):
            boxes.append(f"""            <section class="closing-section">
                <h2 class="closing-label {css}">{label}</h2>
                <p class="closing-content">{sws_inline(day[key])}</p>
            </section>""")
    if not boxes:
        return ""
    return '        <div class="closing-sections">\n' + "\n".join(boxes) + "\n        </div>"


def sws_render_nav(date, all_dates):
    position = all_dates.index(date)
    links = []
    if position > 0:
        previous = all_dates[position - 1]
        links.append(f'<a href="{SWS_REPORT_FILE.format(date=previous)}" rel="prev">'
                     f'← {sws_short_date(dt.date.fromisoformat(previous))}</a>')
    links.append('<a href="archive.html">Archive</a>')
    if position < len(all_dates) - 1:
        following = all_dates[position + 1]
        links.append(f'<a href="{SWS_REPORT_FILE.format(date=following)}" rel="next">'
                     f'{sws_short_date(dt.date.fromisoformat(following))} →</a>')
    return "\n                    ".join(links)


def sws_render_stats(day):
    items = day["items"]
    critical = sum(1 for item in items if item.get("priority") == "critical")
    start = sws_parse_datetime(day["window"]["from"]).astimezone(SWS_TZ)
    end = sws_parse_datetime(day["window"]["to"]).astimezone(SWS_TZ)
    stamp = lambda moment: f"{sws_short_date(moment.date())} {moment:%H:%M}"
    stats = [f'<span class="stat"><span class="stat-value">{len(items)}</span>{"item" if len(items) == 1 else "items"}</span>']
    if critical:
        stats.append(f'<span class="stat is-critical"><span class="stat-value">{critical}</span>critical</span>')
    stats.append(f'<span class="stat">Covers {stamp(start)} → {stamp(end)}</span>')
    return "\n                ".join(stats)


def sws_render_run(day):
    run = day["run"]
    parts = [f"{run['sources_ok']} of {run['sources_total']} sources read",
             f"{run['searches']} search" + ("" if run["searches"] == 1 else "es"),
             sws_plural(run["pages_opened"], "page") + " opened"]
    line = " · ".join(parts)
    if run["failed"]:
        line += "<br>Not reachable today: " + html.escape(", ".join(str(name) for name in run["failed"]))
    return line


def sws_render_report(date, day, categories, all_dates, template, version):
    day_date = dt.date.fromisoformat(date)
    by_id = {item["id"]: item for item in day["items"]}
    headline = by_id[day["top"][0]]["title"] if day["top"] else "A quiet day"
    return sws_fill(template, {
        "date_long": sws_long_date(day_date),
        "description": html.escape(f"{sws_plural(len(day['items']), 'item')}. Top story: {headline}", quote=True),
        "asset_version": version,
        "nav": sws_render_nav(date, all_dates),
        "stats": sws_render_stats(day),
        "top": sws_render_top(day, categories),
        "actions": sws_render_actions(day),
        "categories": sws_render_categories(day, categories),
        "closing": sws_render_closing(day),
        "run": sws_render_run(day),
    })


# ── Archive ──────────────────────────────────────────────────────────────

def sws_legacy_titles(path):
    """Headlines of a report published before the data format existed."""
    text = path.read_text(encoding="utf-8", errors="replace")
    titles = re.findall(r'<h3 class="item-title">(.*?)</h3>', text, re.S)
    titles = [html.unescape(re.sub(r"<[^>]+>", "", title)).strip() for title in titles]
    return [title for title in titles if not SWS_PLACEHOLDER.match(title)]


def sws_ensure_noindex(path):
    """Keep search engines away from pages this script does not render."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if 'name="robots"' in text or '<meta charset="UTF-8">' not in text:
        return False
    path.write_text(text.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n    ' + SWS_NOINDEX, 1),
                    encoding="utf-8")
    return True


def sws_render_archive(entries, weeks, template, version):
    """entries: list of (date, [titles]) for every report, any format."""
    months = {}
    for date, titles in sorted(entries, reverse=True):
        months.setdefault(date[:7], []).append((date, titles))
    blocks = []
    for month, days in months.items():
        rows = []
        for date, titles in days:
            day_date = dt.date.fromisoformat(date)
            items = "".join(
                f'<li data-title="{html.escape(title, quote=True)}"{" hidden" if index >= 3 else ""}>'
                f"{html.escape(title)}</li>" for index, title in enumerate(titles))
            if len(titles) > 3:
                items += f'<li class="archive-more">+ {len(titles) - 3} more</li>'
            if not titles:
                items = '<li class="archive-more">No items</li>'
            rows.append(f"""            <div class="archive-day">
                <a class="archive-day-link" href="{SWS_REPORT_FILE.format(date=date)}">{sws_short_date(day_date)}<span class="archive-day-count">{sws_plural(len(titles), 'item')}</span></a>
                <ul class="archive-titles">{items}</ul>
            </div>""")
        year, number = month.split("-")
        blocks.append(f"""        <section class="archive-month">
            <h2>{SWS_MONTHS[int(number) - 1]} {year}</h2>
{chr(10).join(rows)}
        </section>""")
    total = f"{sws_plural(len(entries), 'report')}, {sum(len(titles) for _, titles in entries)} headlines"
    weeklies = ""
    if weeks:
        rows = "\n".join(
            f'                <li><a href="{SWS_WEEKLY_FILE.format(week=week)}">{html.escape(sws_week_label(digest))}</a>'
            f'<span>{sws_inline(digest["stories"][0]["title"]) if digest["stories"] else "A quiet week"}</span></li>'
            for week, digest in sorted(weeks.items(), reverse=True))
        weeklies = f"""        <section class="archive-weeklies">
            <h2>Weekly digests</h2>
            <ul class="weekly-list">
{rows}
            </ul>
        </section>"""
    return sws_fill(template, {
        "asset_version": version,
        "total": total,
        "weeklies": weeklies,
        "months": "\n\n".join(blocks),
        "latest": SWS_REPORT_FILE.format(date=max(date for date, _ in entries)) if entries else "index.html",
    })


# ── Weekly digest ────────────────────────────────────────────────────────

def sws_week_days(week):
    """Monday to Friday of an ISO week written like 2026-W47, or None."""
    match = SWS_WEEK_ID.match(week)
    if not match:
        return None
    try:
        monday = dt.date.fromisocalendar(int(match.group(1)), int(match.group(2)), 1)
    except ValueError:
        return None
    return [monday + dt.timedelta(days=offset) for offset in range(5)]


def sws_week_label(digest):
    start, end = dt.date.fromisoformat(digest["from"]), dt.date.fromisoformat(digest["to"])
    number = int(digest["week"].split("-W")[1])
    if start.month == end.month:
        span = f"{start.day} to {end.day} {SWS_MONTHS[end.month - 1]} {end.year}"
    else:
        span = f"{start.day} {SWS_MONTHS[start.month - 1]} to {end.day} {SWS_MONTHS[end.month - 1]} {end.year}"
    return f"Week {number} · {span}"


def sws_load_weeks(weekly_dir, errors):
    weeks = {}
    for path in sorted(weekly_dir.glob("20??-W??.json")):
        try:
            weeks[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"weekly/{path.name}: not valid JSON ({exc})")
    return weeks


def sws_validate_week(week, digest, days):
    """Check one weekly digest. Returns (errors, warnings)."""
    errors, warnings = [], []
    name = f"weekly/{week}.json"
    weekdays = sws_week_days(week)
    if not isinstance(digest, dict) or not weekdays:
        return [f"{name}: the file must be a JSON object named like 2026-W47.json"], warnings
    if digest.get("week") != week:
        errors.append(f"{name}: \"week\" must be {week!r} to match the file name")
    start, end = sws_parse_day(digest.get("from")), sws_parse_day(digest.get("to"))
    if start != weekdays[0] or end not in weekdays:
        errors.append(f"{name}: \"from\" must be {weekdays[0]} (the Monday) and \"to\" the last weekday covered, "
                      f"normally {weekdays[-1]}; copy both from the week.py output")
    sws_check_text(digest, "summary", name, errors, 60, 700)

    known = {f"{date}/{item['id']}" for date, day in days.items() for item in day.get("items", [])}
    stories = digest.get("stories")
    if not isinstance(stories, list) or len(stories) > 5:
        errors.append(f"{name}: \"stories\" must be a list of at most 5 stories")
        stories = []
    ids = set()
    for number, story in enumerate(stories, 1):
        if not isinstance(story, dict):
            errors.append(f"{name}: stories[{number}] must be an object")
            continue
        where = f"{name}: story {number} ({story.get('id', 'no id')})"
        if not isinstance(story.get("id"), str) or not SWS_ID.match(story["id"]) or story["id"] in ids:
            errors.append(f"{where}: \"id\" must be a short slug, unique in the digest")
        ids.add(story.get("id"))
        sws_check_text(story, "title", where, errors, 10, 110)
        sws_check_text(story, "what", where, errors, 60, 900)
        sws_check_text(story, "now", where, errors, 30, 500)
        sws_check_text(story, "why", where, errors, 20, 450)
        sws_check_url(story.get("now_url"), where, errors)
        refs = story.get("items")
        if not isinstance(refs, list):
            errors.append(f"{where}: \"items\" must be a list of references such as \"2026-11-19/item-id\"")
            refs = []
        for ref in refs:
            if ref not in known:
                errors.append(f"{where}: \"{ref}\" is not an item of a daily edition; copy the reference "
                              "from the week.py output")
        for key in ("title", "what", "now", "why"):
            if isinstance(story.get(key), str) and SWS_HEDGE.search(story[key]):
                warnings.append(f"{where}: \"{key}\" hedges about something unconfirmed. Leave it out instead")

    actions = digest.get("actions", [])
    if not isinstance(actions, list) or len(actions) > 5:
        errors.append(f"{name}: \"actions\" must be a list of at most 5 things still to do")
        actions = []
    for number, action in enumerate(actions, 1):
        where = f"{name}: action {number}"
        if not isinstance(action, dict):
            errors.append(f"{where} must be an object")
            continue
        sws_check_text(action, "title", where, errors, 8, 110)
        sws_check_text(action, "detail", where, errors, 20, 500)
        if not sws_parse_day(action.get("opened")):
            errors.append(f"{where}: \"opened\" must be the date the action first appeared")
        if action.get("url") is not None:
            sws_check_url(action.get("url"), where, errors)

    missed = digest.get("missed", [])
    if not isinstance(missed, list) or len(missed) > 3:
        errors.append(f"{name}: \"missed\" must be a list of at most 3 items")
        missed = []
    for number, item in enumerate(missed, 1):
        where = f"{name}: missed item {number}"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        sws_check_text(item, "title", where, errors, 10, 110)
        sws_check_text(item, "summary", where, errors, 40, 700)
        sws_check_text(item, "why", where, errors, 20, 450)
        sws_check_text(item, "source", where, errors, 2, 60)
        sws_check_url(item.get("url"), where, errors)
        published = sws_parse_day(item.get("published"))
        if not published or not (weekdays[0] - dt.timedelta(days=2) <= published <= weekdays[-1] + dt.timedelta(days=2)):
            errors.append(f"{where}: \"published\" must be a date inside the week")

    ahead = digest.get("ahead", [])
    if not isinstance(ahead, list) or len(ahead) > 8:
        errors.append(f"{name}: \"ahead\" must be a list of at most 8 dated events")
        ahead = []
    for number, event in enumerate(ahead, 1):
        where = f"{name}: coming-up entry {number}"
        if not isinstance(event, dict):
            errors.append(f"{where} must be an object")
            continue
        date = sws_parse_day(event.get("date"))
        if not date or (end and not (end <= date <= end + dt.timedelta(days=60))):
            errors.append(f"{where}: \"date\" must fall within 60 days after the week")
        sws_check_text(event, "title", where, errors, 8, 110)
        sws_check_text(event, "detail", where, errors, 10, 300, required=False)
        sws_check_url(event.get("url"), where, errors)

    long_read = digest.get("long_read")
    if long_read is not None:
        where = f"{name}: long_read"
        if not isinstance(long_read, dict):
            errors.append(f"{where} must be an object or left out")
        else:
            sws_check_text(long_read, "title", where, errors, 8, 140)
            sws_check_text(long_read, "source", where, errors, 2, 60)
            sws_check_text(long_read, "why", where, errors, 20, 400)
            sws_check_url(long_read.get("url"), where, errors)

    run = digest.get("run")
    if not isinstance(run, dict) or not all(isinstance(run.get(key), int) for key in ("searches", "pages_opened")):
        errors.append(f"{name}: \"run\" must give \"searches\" and \"pages_opened\" as whole numbers")
    return errors, warnings


def sws_week_health(digest, days, legacy):
    """One row per weekday covered: (date, status text, link or None, is a problem)."""
    rows = []
    day = dt.date.fromisoformat(digest["from"])
    end = dt.date.fromisoformat(digest["to"])
    while day <= end:
        date = day.isoformat()
        if date in days:
            count = len(days[date]["items"])
            failed = days[date]["run"]["failed"]
            status = sws_plural(count, "item")
            if failed:
                status += f", {sws_plural(len(failed), 'source')} not reachable"
            rows.append((day, status, SWS_REPORT_FILE.format(date=date), count < SWS_THIN_BELOW))
        elif date in legacy:
            rows.append((day, f"{sws_plural(len(legacy[date]), 'item')}, older format",
                         SWS_REPORT_FILE.format(date=date), False))
        else:
            rows.append((day, "no edition published", None, True))
        day += dt.timedelta(days=1)
    return rows


def sws_render_week(week, digest, days, legacy, all_weeks, template, version):
    items = {f"{date}/{item['id']}": (date, item) for date, day in days.items() for item in day["items"]}

    stories = []
    for story in digest["stories"]:
        refs = []
        for ref in story["items"]:
            date, item = items[ref]
            edition = f'{SWS_REPORT_FILE.format(date=date)}#item-{item["id"]}'
            refs.append(f'                    <li>{sws_external_link(item["url"], sws_inline(item["title"]))} · '
                        f'<a href="{edition}">{sws_short_date(dt.date.fromisoformat(date))} edition</a></li>')
        ref_list = ('\n                <ul class="story-items">\n' + "\n".join(refs) + "\n                </ul>") if refs else ""
        stories.append(f"""            <article class="story" id="story-{story['id']}">
                <h3>{sws_inline(story['title'])}</h3>
                <p class="story-part"><span class="story-label">What happened</span>{sws_inline(story['what'])}</p>
                <p class="story-part"><span class="story-label">Where it stands</span>{sws_inline(story['now'])} {sws_external_link(story['now_url'], 'Source', 'item-source')}</p>
                <p class="item-why"><strong>Why it matters:</strong> {sws_inline(story['why'])}</p>{ref_list}
            </article>""")
    stories_html = ""
    if stories:
        stories_html = ('        <h2 class="section-title">Stories of the week</h2>\n        <div class="stories">\n'
                        + "\n".join(stories) + "\n        </div>")

    actions = digest.get("actions") or []
    if actions:
        rows = []
        for action in actions:
            meta = [f"Open since {sws_short_date(dt.date.fromisoformat(action['opened']))}"]
            if action.get("url"):
                meta.append(sws_external_link(action["url"], "details"))
            rows.append(f"""                <li>
                    <div class="action-title">{sws_inline(action['title'])}</div>
                    <p class="action-detail">{sws_inline(action['detail'])}</p>
                    <p class="action-meta">{' · '.join(meta)}</p>
                </li>""")
        actions_html = f"""        <section class="panel panel-actions" aria-labelledby="actionsTitle">
            <h2 class="panel-title" id="actionsTitle">Still to do</h2>
            <ul class="action-list">
{chr(10).join(rows)}
            </ul>
        </section>"""
    else:
        actions_html = """        <section class="panel panel-actions is-clear" aria-labelledby="actionsTitle">
            <h2 class="panel-title" id="actionsTitle">Still to do</h2>
            <p>Nothing is left over from this week.</p>
        </section>"""

    missed_html = ""
    if digest.get("missed"):
        cards = []
        for item in digest["missed"]:
            published = dt.date.fromisoformat(item["published"])
            cards.append(f"""            <article class="item">
                <div class="item-header">
                    <h3 class="item-title">{sws_external_link(item['url'], sws_inline(item['title']))}</h3>
                </div>
                <p class="item-summary">{sws_inline(item['summary'])}</p>
                <p class="item-why"><strong>Why it matters:</strong> {sws_inline(item['why'])}</p>
                <p class="item-meta">{sws_external_link(item['url'], 'via ' + html.escape(item['source'].strip()), 'item-source')} · published <time datetime="{published}">{sws_short_date(published)}</time></p>
            </article>""")
        missed_html = ('        <h2 class="section-title">Not in the daily editions</h2>\n        <div class="items-list">\n'
                       + "\n".join(cards) + "\n        </div>")

    ahead_html = ""
    if digest.get("ahead"):
        rows = []
        for event in sorted(digest["ahead"], key=lambda e: e["date"]):
            date = dt.date.fromisoformat(event["date"])
            detail = f' <span class="ahead-detail">{sws_inline(event["detail"])}</span>' if event.get("detail") else ""
            rows.append(f'                <li><time class="ahead-date" datetime="{date}">{sws_short_date(date)}</time>'
                        f'<span>{sws_external_link(event["url"], sws_inline(event["title"]))}{detail}</span></li>')
        ahead_html = f"""        <section class="panel" aria-labelledby="aheadTitle">
            <h2 class="panel-title" id="aheadTitle">Coming up</h2>
            <ul class="ahead-list">
{chr(10).join(rows)}
            </ul>
        </section>"""

    read_html = ""
    if digest.get("long_read"):
        read = digest["long_read"]
        read_html = f"""        <section class="panel" aria-labelledby="readTitle">
            <h2 class="panel-title" id="readTitle">One thing worth reading in full</h2>
            <p class="read-title">{sws_external_link(read['url'], sws_inline(read['title']))} <span class="ahead-detail">{html.escape(read['source'].strip())}</span></p>
            <p class="action-detail">{sws_inline(read['why'])}</p>
        </section>"""

    health_rows = []
    for day, status, link, problem in sws_week_health(digest, days, legacy):
        label = f'<a href="{link}">{sws_short_date(day)}</a>' if link else sws_short_date(day)
        css = ' class="is-problem"' if problem else ""
        health_rows.append(f'                <li{css}><span class="ahead-date">{label}</span><span>{html.escape(status)}</span></li>')
    health_html = f"""        <section class="panel" aria-labelledby="healthTitle">
            <h2 class="panel-title" id="healthTitle">This week's editions</h2>
            <ul class="ahead-list health-list">
{chr(10).join(health_rows)}
            </ul>
        </section>"""

    position = all_weeks.index(week)
    nav = []
    if position > 0:
        previous = all_weeks[position - 1]
        nav.append(f'<a href="{SWS_WEEKLY_FILE.format(week=previous)}" rel="prev">← Week {int(previous.split("-W")[1])}</a>')
    nav.append('<a href="archive.html">Archive</a>')
    if position < len(all_weeks) - 1:
        following = all_weeks[position + 1]
        nav.append(f'<a href="{SWS_WEEKLY_FILE.format(week=following)}" rel="next">Week {int(following.split("-W")[1])} →</a>')
    else:
        nav.append('<a href="index.html">Latest daily →</a>')

    run = digest["run"]
    return sws_fill(template, {
        "week_label": html.escape(sws_week_label(digest)),
        "description": html.escape(digest["summary"].strip()[:200], quote=True),
        "asset_version": version,
        "nav": "\n                    ".join(nav),
        "summary": sws_inline(digest["summary"]),
        "stories": stories_html,
        "actions": actions_html,
        "missed": missed_html,
        "ahead": ahead_html,
        "long_read": read_html,
        "health": health_html,
        "run": f"{run['searches']} search" + ("" if run["searches"] == 1 else "es")
               + f" · {sws_plural(run['pages_opened'], 'page')} opened",
    })


# ── Main ─────────────────────────────────────────────────────────────────

def sws_write(path, text):
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def sws_main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="validate the data files without writing anything")
    parser.add_argument("--data", type=Path, default=SWS_ROOT / "data", help="directory holding the data files")
    parser.add_argument("--out", type=Path, default=SWS_ROOT, help="directory to write the site to (for previews)")
    args = parser.parse_args()

    categories = sws_load_categories()
    errors, warnings = [], []
    days = sws_load_days(args.data, errors)
    earlier_urls = {}
    for date, day in days.items():
        day_errors, day_warnings = sws_validate_day(date, day, categories, earlier_urls)
        errors += day_errors
        # Only the newest file is being written today; older warnings are history.
        if date == max(days):
            warnings += day_warnings
        if not day_errors:
            for item in day["items"]:
                earlier_urls.setdefault(item["url"], date)

    weeks = sws_load_weeks(args.data / "weekly", errors)
    for week, digest in weeks.items():
        week_errors, week_warnings = sws_validate_week(week, digest, days)
        errors += week_errors
        if week == max(weeks):
            warnings += week_warnings

    for message in warnings:
        print(f"warning: {message}")
    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
        sys.exit(f"\n{len(errors)} problem(s) found. Nothing was written. Fix the data file and run again.")
    if args.check:
        print(f"OK: {sws_plural(len(days), 'data file')} and {sws_plural(len(weeks), 'weekly digest')} valid.")
        return

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if out != SWS_ROOT:
        shutil.copytree(SWS_ROOT / "assets", out / "assets", dirs_exist_ok=True)

    legacy, tagged = {}, 0
    for path in sorted(SWS_ROOT.glob(SWS_REPORT_GLOB)):
        date = path.name[:10]
        if date not in days:
            legacy[date] = sws_legacy_titles(path)
            if out == SWS_ROOT:
                tagged += sws_ensure_noindex(path)
    if out == SWS_ROOT and (SWS_ROOT / "daily-tech-watch-template.html").exists():
        tagged += sws_ensure_noindex(SWS_ROOT / "daily-tech-watch-template.html")

    version = sws_asset_version()
    all_dates = sorted(set(days) | set(legacy))
    report_template = (SWS_ROOT / "templates" / "report.html").read_text(encoding="utf-8")
    written = 0
    for date, day in days.items():
        page = sws_render_report(date, day, categories, all_dates, report_template, version)
        written += sws_write(out / SWS_REPORT_FILE.format(date=date), page)

    weekly_template = (SWS_ROOT / "templates" / "weekly.html").read_text(encoding="utf-8")
    all_weeks = sorted(weeks)
    for week, digest in weeks.items():
        page = sws_render_week(week, digest, days, legacy, all_weeks, weekly_template, version)
        written += sws_write(out / SWS_WEEKLY_FILE.format(week=week), page)

    entries = [(date, [item["title"] for item in day["items"]]) for date, day in days.items()]
    entries += list(legacy.items())
    archive_template = (SWS_ROOT / "templates" / "archive.html").read_text(encoding="utf-8")
    written += sws_write(out / "archive.html", sws_render_archive(entries, weeks, archive_template, version))

    if all_dates:
        newest = all_dates[-1]
        source = (out if newest in days else SWS_ROOT) / SWS_REPORT_FILE.format(date=newest)
        written += sws_write(out / "index.html", source.read_text(encoding="utf-8"))

    print(f"Built {sws_plural(len(days), 'report')} and {sws_plural(len(weeks), 'weekly digest')} from data, "
          f"{len(legacy)} older reports listed in the archive, {sws_plural(written, 'file')} changed.")
    if tagged:
        print(f"Added the noindex tag to {sws_plural(tagged, 'older page')} (they had none).")
    if days:
        print(f"Newest daily: {SWS_REPORT_FILE.format(date=max(days))}")
    if weeks:
        print(f"Newest weekly: {SWS_WEEKLY_FILE.format(week=max(weeks))}")


if __name__ == "__main__":
    sws_main()
