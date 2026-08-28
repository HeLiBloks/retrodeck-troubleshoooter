# Scraping troubleshooting

Distilled from the retrodeck-scraper project, which is the tool these findings came out
of. Read that repo's `CLAUDE.md` for the matcher's own reasoning; this file is what you
need when a scrape has gone wrong.

## Why an external scraper at all

RetroDECK does **no scraping itself** — it ships ES-DE and delegates entirely to ES-DE's
built-in scraper, which:

1. is **strictly sequential** — one API request at a time, no thread setting exists, so a
   multi-thread ScreenScraper allowance is wasted;
2. is **rate-limited server-side** (anonymous: 1 thread, often refused; registered: ~20k
   requests/day; supporters: more threads and quota);
3. **re-scrapes by default** — "Scrape these games: All games" hits the API for every game.
   The in-app fix is **"Scrape these games" → "No metadata"** with "Overwrite files and
   data" off.

## Failures that report success

This is the category that costs whole days, so it comes first.

### Quota exhaustion exits 0

All four messages Skyscraper prints before giving up leave the exit status at **zero**, so
the log text is the only signal there is. Match them as **full sentences** — short
substrings both miss two of the messages and false-positive on game descriptions, one of
which really does contain "Get a bigger quota!":

```
you have exceeded your daily quota
the screenscraper api is currently closed
currently closed or too busy
maximum number of requests per day
```

The right response is not to retry: generate from the cache now at **no API cost**, and
gather again tomorrow with `--flags onlymissing`, which skips everything already cached.

`rdtroubleshoot scraping` scans any `*.log` beside the scraper checkout for these.

### `userCreds="user:"` is worse than anonymous

A half-set credential makes Skyscraper send an **empty password on every request**. Login is
refused, the run scrapes nothing, and repeated bad logins carry a blacklist risk. It once
cost a silent 4–5 hour `nohup`'d run. `rdtroubleshoot scraping` reports it **FAIL**, not
WARN, for that reason.

Two related things about credentials:

- **Skyscraper does not URL-encode the password.** It builds the query as
  `"&sspassword=" + password`, raw. A password containing `" $ ; > &` is hazardous — `;` can
  act as a query-parameter separator server-side. A pre-encoded password was also rejected.
  Use an alphanumeric one.
- `config.ini` holds the password in cleartext and should be `chmod 600`.

### Writing a gamelist while RetroDECK is open

ES-DE flushes every gamelist on exit, so a scrape that finishes against an open RetroDECK
reports success and loses the lot — and the `.bak.*` it took is from *before* the
enrichment. Every gamelist writer must refuse. `rdtroubleshoot emulation` tells you whether
it is open.

Gathering into the resource cache is safe at any time; only `generate` and `enrich` write
gamelists.

## Skyscraper's two phases, and which one costs quota

| phase | command | cost | safe while RetroDECK runs |
|---|---|---|---|
| gather | `Skyscraper -p <platform> -s screenscraper` | API requests | yes |
| generate | `Skyscraper -p <platform>` (no `-s`) | none | **no** |

So a quota-exhausted run is never wasted: the cache is durable and `generate` publishes
from it for free.

**A 52-byte stub `db.xml`** in `~/.skyscraper/cache/<platform>/` means that platform's cache
is empty, so a `generate` there has nothing to publish and needs a quota-spending gather
first. `rdtroubleshoot scraping` names those platforms — knowing beforehand is the
difference between a plan and a surprise.

## Generation does not lose metadata, unless the paths disagree

Skyscraper's `esde` frontend inherits `preserveFromOld`, which refills every empty field
from the old gamelist (desc, rating, genre, developer, publisher, players) and preserves
ES-DE's own `favorite`/`hidden`/`kidgame`/`playcount`/`lastplayed`/`sortname`/`altemulator`.
Verified: 59 descriptions before, 59 after.

**But that matching is on the raw `<path>` string.** See the `/home` vs `/var/home` trap in
[EMULATION.md](EMULATION.md) — it is the single most expensive bug in the project, and
`rdtroubleshoot emulation` checks every gamelist for it.

A corollary: `preserveFromOld` carries only the fields Skyscraper knows about, so a **custom
tag in a gamelist is dropped on the next generate**. Never store anything there you cannot
rebuild.

## Descriptions were never the whole gap

The lesson worth carrying: one enrich run took an arcade folder's `<genre>` coverage from
**55% to 99%** while its descriptions barely moved. That folder had been reading **98%
described and 45% un-genred at the same time**, and a source carrying no prose at all closed
most of the gap. Publisher told the same story, ending at 91% against those 98% descriptions.

So when judging coverage, count the structured tags too. `rdtroubleshoot scraping` reports
per-tag counts per system, worst-covered first, rather than a single "described" percentage.

Same shape in a DOS folder: **fully described** while genre sat at 60% and players at 46%,
because roughly two entries in five matched no database record at all — the filenames
carried the subtitle, publisher and year that the bare title did not.

## The rules any metadata source here must obey

These are the invariants the scraper enforces; if you are debugging a wrong value, this is
the frame.

- **Never overwrite a value the tool did not write.** A value `enrich` declines to write is
  a value it cannot take back. New sources fill blanks; `--overwrite` is the opt-in. The
  corollary is that **fixing the matcher does not fix the gamelists** — a wrong description
  written by an old version is still there, and removing it is a separate, opt-in pass.
- **A failure with no verdict must not be cached as a verdict.** A 5xx, a timeout or no
  route is not "the database does not have it". Caching those for 30 days silently disables
  a source with no warning afterwards.
- **Agreeing on a normalized title is not agreeing on a game.** The release year is
  usually the only thing in the data that separates two products with one name.
- **A canon or a filename bridge may fill structured tags without being trusted for prose.**
  MAME's romset name is an exact key, so facts keyed on it need no identity check; a title
  matched by name does.

## Quick triage

```sh
rdtroubleshoot scraping                 # creds, cache, backups, quota, coverage
rdtroubleshoot emulation                # is RetroDECK open, do the gamelists parse
rdtroubleshoot scraping emulation -q    # only what to act on
```

Then, in the scraper checkout itself:

```sh
./retrodeck-scrape.py health            # its own pre-flight
./retrodeck-scrape.py status
./retrodeck-scrape.py enrich --dry-run  # report, write nothing
./retrodeck-scrape.py missing --resource cover
```
