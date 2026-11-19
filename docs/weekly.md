# Weekly Tech Digest: how to produce one

You are writing this week's digest of the Daily Tech Watch. Read `docs/routine.md` first: the reader, the rules that always hold, and how to read a page are the same here, and this file does not repeat them. Then read this file to the end before you start.

## What the digest is for

Every weekday the reader gets a list of what happened. On Friday afternoon he wants something different: one page, five minutes, that tells him

1. what actually mattered this week, once the noise is gone;
2. where those stories stand **today**, not on the day they were reported;
3. what he still has to do;
4. what is coming in the next few weeks;
5. whether the daily briefing itself worked.

So the digest is an editor's view of the week, not a second copy of the daily items. Its value comes from three things the daily editions cannot do: joining items into stories, going back to see what happened next, and looking for what was missed.

A normal run reads 10 to 15 pages and runs 5 to 10 searches.

## Step 1: Gather the week

Work in the repository root. Run:

```bash
python3 scripts/week.py --out /tmp/tech-watch-week.txt
```

Read the whole file. It gives you the week's identifier and dates, the state of each weekday edition, every item published with its reference (such as `2026-11-19/wordpress-7-1-5`), the actions raised, last week's digest, and the most-discussed Hacker News stories that no edition covered.

If it says this week's digest file already exists, the digest is published: stop and say so. Editions marked "old format" give headlines only; use them as leads. The material counts the problems with the week's editions itself; go by its count (Step 10).

## Step 2: Choose the stories of the week

Pick **3 to 5 stories**; fewer in a thin week, and never more than 5. A story is a development, not an item: several items over several days often make one story ("a heavy patching week: WordPress, PHP and NGINX"), and most items make none.

Rank by what it means for him: something he must act on first, then changes to the tools he works with, then the big stories in tech. If last week's digest left a story open and it moved this week, it can return.

## Step 3: Find out where each story stands today

This is the step that makes the digest worth reading. For each story, find out what happened since the first report: a fix released or replaced, attacks confirmed, a date moved, a decision reversed, a notable reaction.

- Read pages first, with `scripts/page.py`: the primary source again (advisories and release pages get updated), the vendor's or researcher's own write-up, the newest solid report. This is where follow-ups usually turn something up.
- Then at most one search per story, for the part most likely to have moved. Skip it when the pages already answered the question. Searches often return old results for recent events; use extended mode as `docs/routine.md` describes, and never let a search summary overrule a page.

Write the result in `now`, and set `now_url` to the one page that supports it. Every fact in `now` must be on that page, so choose the page that carries the most important update and keep `now` to what it says. If nothing changed, say that plainly and link the page that shows the current state. Follow up on last week's open stories and "coming up" dates the same way when they are still relevant.

## Step 4: Look for what was missed

Two sources:

- the Hacker News list in the material, which is the better lead (most of it will not matter to this reader, and some of it was covered through another site);
- up to four searches for the week's biggest stories: in tech generally, in AI, in WordPress, and for French small companies.

Include **at most 3** things that clearly belonged in a daily edition and were not there. Usually it is none or one. Each one follows the daily rules: read the page, take the facts and the date from it. Link the primary source, or an established publication when the primary page will not open; not a site that only rewrites announcements. Do not fill this section to make it look useful; an empty one means the daily editions did their job.

## Step 5: Decide what is still to do

Start from "actions raised this week" in the material. He cannot tick anything off, so assume an action is still open unless the follow-up in Step 3 shows it no longer applies (a newer fix replaced it, the deadline passed). Keep at most 5, most urgent first, and reword one if the week changed what he should do. Add a new action only when Step 3 turned up something he must do.

## Step 6: List what is coming

Dated events in the next six weeks or so that matter to him: releases of the tools he uses, end-of-support and deprecation dates, legal and tax deadlines in France, a launch everyone will talk about. Up to 8, and often 2 or 3.

Each entry needs a date you read on a page today, and that page as its link. The week's items are the first place to look (many mention dates), then the pages the material lists under "pages that list upcoming dates". No date from memory.

## Step 7: Optionally, one thing worth reading in full

If one piece you read this week deserves fifteen minutes of his weekend (an analysis, a post-mortem, a tutorial he can apply), name it in `long_read` and say why in a sentence. If nothing stands out, leave the field out.

## Step 8: Write the data file

Write `data/weekly/<week>.json`, where `<week>` is the identifier from the material. All text is plain text, with `backticks` for code. The example is invented and shows the shape only.

```json
{
  "week": "2026-W03",
  "from": "2026-01-12",
  "to": "2026-01-16",
  "summary": "Two or three sentences on the week as a whole: what dominated it and what it leaves him with. Written last.",
  "stories": [
    {
      "id": "example-patching-week",
      "title": "A patching week: Example Forms, then the hosts",
      "what": "Two to four sentences joining the week's items into one account: what happened, in order, with the facts that matter.",
      "now": "One or two sentences on where it stands today. For example: the vendor confirmed attacks on 15 Jan and released 3.2.2, which replaces 3.2.1.",
      "now_url": "https://example.com/advisories/example-forms-3-2-2",
      "why": "One or two sentences on what it means for him now.",
      "items": ["2026-01-13/example-plugin-flaw", "2026-01-15/example-host-update"]
    }
  ],
  "actions": [
    {
      "title": "Update Example Forms to 3.2.2 on every client site",
      "detail": "3.2.1 turned out to be incomplete; 3.2.2 is the fixed version.",
      "opened": "2026-01-13",
      "url": "https://example.com/advisories/example-forms-3-2-2"
    }
  ],
  "missed": [],
  "ahead": [
    {
      "date": "2026-01-27",
      "title": "Example CMS 9.0 release",
      "detail": "Drops support for PHP 8.1.",
      "url": "https://example.com/roadmap"
    }
  ],
  "long_read": {
    "title": "How the Example Forms attack worked, step by step",
    "url": "https://example.com/blog/example-forms-post-mortem",
    "source": "Example Security",
    "why": "It shows how the flaw was found in logs, which you can check for on your own sites."
  },
  "run": { "searches": 7, "pages_opened": 12 }
}
```

Fields:

- `week`, `from`, `to`: copy from the top of the material. `to` is the last weekday the digest covers, normally the Friday.
- `stories[].items`: the references of the daily items the story is built from, copied exactly from the material. It may be empty for a story drawn from old-format editions.
- `stories[].now_url`: a page you read **today**.
- `actions[].opened`: the date the action first appeared in a daily edition, or today's date for a new one.
- `missed[]`: `title`, `summary`, `why`, `url`, `source` and `published`, written as for a daily item.
- `ahead[].date`: the date of the event, inside the next 60 days.
- `long_read`: leave the whole field out when there is none.
- `run`: how many searches you ran, and how many different pages you read successfully (a failed attempt does not count, and a page read twice counts once).

The page also shows a table of the week's editions (which days were published, how many items, which sources failed). The build writes it from the data; you do not.

Writing: as in `docs/routine.md`. In addition, `what` tells the story in order and in full sentences, and `now` starts from today ("As of 20 Nov, …" is fine). Do not repeat a daily item's summary word for word.

## Step 9: Build, check, publish

```bash
python3 scripts/build.py
```

```bash
python3 scripts/verify.py <week>
```

Fix every error from the build. The check opens each `now_url`, each missed item's link and each "coming up" link, and lists figures it cannot find there; look at each one again, as for a daily edition, and run the build again after any change. Then publish as a daily edition is published:

```bash
git add -A
git commit -m "Add weekly digest for <week>"
git push -u origin "$(git branch --show-current)"
```

Open a pull request from that branch into `main` with the GitHub tools and merge it straight away with the squash method. If the push or the merge fails, retry once, then report the failure in your final message.

## Step 10: Final message

It goes to his phone. On a normal week:

```
Weekly digest W03 (12 to 16 Jan): 4 stories
1. <first story title>
2. <second story title>
3. <third story title>
Still to do: 2
https://adrien-robert.github.io/daily-tech-watch/2026-W03-weekly-digest.html
```

Leave out "Still to do" when the list is empty, and list at most three stories.

When the material counts one or more problems with the week's editions (a missing or thin day; old-format days are not problems), or the gathering or publishing failed, start the first line with ⚠️ and put the cause on a second line, in one plain sentence of at most 140 characters:

```
⚠️ Weekly digest W03 (12 to 16 Jan): 3 stories
No daily edition was published on Wed 14 Jan.
1. <first story title>
…
```

This line is how he learns that the daily briefing has stopped working, so state it plainly whenever it applies.
