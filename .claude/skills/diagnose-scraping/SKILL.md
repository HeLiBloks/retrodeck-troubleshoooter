---
name: diagnose-scraping
description: Diagnose ROM metadata and artwork scraping problems - a scrape that produced nothing, missing descriptions or genres, wrong descriptions, ScreenScraper credential or quota failures, or an empty Skyscraper resource cache. Use before running or re-running any scrape.
---

# Diagnosing a scraping problem

The defining hazard here is that **the expensive failures report success**. A quota-exhausted
run exits 0. A half-set credential scrapes nothing for four hours and exits 0. A gamelist
written while RetroDECK is open is silently discarded on exit. So check before running, not
after.

## 0. Before anything: check what is already known

```sh
rdtroubleshoot kb search "<the user's words>"
rdtroubleshoot --kb            # annotates each WARN/FAIL with the entries covering it
```

A hit in `errors/` means the answer is already written — reply from its TL;DR. A hit in
`backlog/` means it is known and unresolved, which is still a real answer. Full procedure in
the `kb-lookup` skill; recording what you find is in `document-finding`.

## 1. Always start here

```sh
./rdtroubleshoot scraping emulation
```

`emulation` is not optional in that line: it is what tells you whether RetroDECK is open,
which decides whether anything may write a gamelist at all.

In the scraper checkout itself:

```sh
./retrodeck-scrape.py health
./retrodeck-scrape.py enrich --dry-run     # reports, writes nothing
```

## 2. Match the symptom

| symptom | cause to check first |
|---|---|
| a long run scraped **nothing** | `userCreds="user:"` — half-set, worse than anonymous. **FAIL** |
| run stopped early, exit 0 | **quota**; all four messages exit 0, so only the log text says so |
| `generate` published nothing | that platform's cache is a **52-byte stub `db.xml`**; it needs a gather |
| metadata **vanished** after a run | the gamelist was written while RetroDECK was open, or the `/home` vs `/var/home` path mismatch |
| descriptions fine, **genres empty** | normal and worth fixing — see below |
| a **wrong** description | an old run wrote it; the matcher fix does not retract it |
| art missing for one ROM | ES-DE matches media by **filename**, and the probe must glob the stem, not guess a suffix |

## 3. Coverage: count the structured tags, not just descriptions

A folder that looks 98% described can be 45% un-genred. Measured on an arcade folder: genre
coverage went from **55% to 99%** in one run, against descriptions that barely moved.
`rdtroubleshoot scraping` reports per-tag counts per system, worst first, for exactly this
reason.

So "fully described" is not "this folder is done".

## 4. Spending quota is the thing to be careful about

- **Gather is the only phase that costs requests.** `generate` builds gamelists and media
  from the cache for free, so a quota-exhausted day is never wasted work.
- Resume with `--flags onlymissing`, which skips everything already cached.
- Free tier is ~20k requests/day and **1 thread**. Do not use API calls to test CLI
  plumbing — the parent project ships a stub Skyscraper for that.
- `--dry-run` writes nothing: no gamelist and **no media** either, which is the half that is
  easy to forget.

## 5. The invariants any fix must respect

- **Never overwrite a value the tool did not write.** New sources fill blanks; `--overwrite`
  is the opt-in. A value declined is a value that cannot be taken back — which is also why
  fixing the matcher never repairs existing gamelists.
- **A network failure is not a verdict.** A 5xx, a timeout or no route must not be cached as
  "not found"; doing so silently disables a source for its whole cache lifetime.
- **A normalized title match is not an identity.** The release year is usually the only
  thing separating two different products with the same name.
- **Match per entry, never by description text.** The paragraph that is wrong on one game is
  the right one on another, so a text-keyed sweep deletes it from both.

Full background: [docs/SCRAPING.md](../../../docs/SCRAPING.md).
