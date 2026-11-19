# Daily Tech Watch

A daily tech briefing by **Stellar Web Solutions**: the day's important tech news, plus depth on AI, Claude Code, WordPress, Bricks Builder, web development and French agency business.

- **Latest edition:** https://adrien-robert.github.io/daily-tech-watch/
- **Archive with search:** https://adrien-robert.github.io/daily-tech-watch/archive.html
- **By date:** `https://adrien-robert.github.io/daily-tech-watch/YYYY-MM-DD-daily-tech-report.html`

## How an edition is made

A scheduled Claude Code task runs every weekday morning and follows [`docs/routine.md`](docs/routine.md):

1. `scripts/collect.py` reads the feeds listed in `config/sources.json` and lists everything published since the last edition, with real dates.
2. Claude reads the pages that have no feed, runs searches for what feeds miss, and reads the page behind every story it keeps (`scripts/page.py`).
3. Claude writes the day as one data file, `data/YYYY-MM-DD.json`.
4. `scripts/build.py` validates that file and renders the report page, `index.html` and `archive.html`.
5. The result is merged into `main`, which publishes it through GitHub Pages.

## What lives where

| Path | What it is |
|---|---|
| `docs/routine.md` | The instructions the scheduled task follows. Edit this to change what the briefing covers or how it is written. |
| `config/sources.json` | The feeds and pages checked every day, and the section names. |
| `data/` | One JSON file per edition. The source of truth for every report page. |
| `scripts/collect.py` | Fetches the feeds and prints the candidates for the day. |
| `scripts/page.py` | Opens one web page and prints its publication dates and text, for checking a story. |
| `scripts/build.py` | Validates the data and renders the site. |
| `templates/`, `assets/` | Page layout, styles and scripts shared by every report. |
| `YYYY-MM-DD-daily-tech-report.html`, `index.html`, `archive.html` | Generated pages. Do not edit them by hand. |

Reports dated before 2026-11-19 were written directly as HTML by an earlier version of the task. They are kept as they are and listed in the archive.

## Running it by hand

The scripts use only the Python standard library.

```bash
python3 scripts/collect.py --out /tmp/tech-watch-candidates.txt
```

```bash
python3 scripts/build.py
```

`python3 scripts/build.py --check` validates the data files without writing anything. `--out <folder>` renders a preview somewhere else.

After changing a template or a stylesheet, run `scripts/build.py` once: it re-renders every report that has a data file.
