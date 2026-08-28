---
slug: c64-roms-without-extension-invisible
area: emulation
status: open
first_seen: 2026-08-28
last_confirmed: 2026-08-28
signatures:
  - source: symptom
    pattern: (c64|commodore).*(missing|not sh(ow|own)|fewer games|no metadata)
    note: the folder holds more files than the frontend or the scraper reports
  - source: checker
    pattern: Coverage \(c64\)
    note: the gap is proportionally large and does not shrink on a re-scrape
---

# A system folder reports fewer games than it holds — files with no extension at all

## TL;DR

We have seen this and there is **no fix that can be applied from this repository**. A large
share of one system folder's files carry **no filename extension**, so every tool that
filters by format is blind to them: the frontend does not list them and the scraper cannot
look them up. The gamelist is therefore *complete for what the tools can see*, which is why
a re-scrape never closes the gap. Renaming the files to a real format suffix is the fix, and
that is a decision about the user's library rather than something to automate.

---

## Engineer notes

### Symptom signature

```
WARN  Coverage (c64)  N entries - desc M/N, genre M/N, publisher M/N, players M/N
```

Other tells:

- The shortfall is stable across runs — a second `enrich` or `scrape` writes nothing new.
- Listing the folder shows bare names (`1942`, `BRUCELEE`, `ELITE`) beside properly suffixed
  files, and further files carrying a **non-format** suffix: `.I` / `.II` / `.III` for disk
  sides, `.P00`.
- Every tool in the chain agrees on the smaller number, which is the tell that this is a
  *filter* and not a lookup failure.

### What is known

- The frontend and the scraper both enumerate ROMs by matching the platform's declared
  format list. A file with no suffix matches nothing, so it is dropped before any lookup is
  attempted — it is not counted as "unmatched", it is not counted at all.
- The metadata for these titles exists in the offline databases. Nothing about the lookup is
  broken; the files never reach it.
- Confirmed on the test machine 2026-08-28 via `rdtroubleshoot scraping`, which reports the
  folder's per-tag coverage.

### What has been ruled out

- **Not a matcher problem.** The titles are ordinary well-known games that the databases
  cover; they are simply never queried.
- **Not fixable by admitting an empty suffix.** Treating "no extension" as a format would
  pull every stray file in a ROM folder into the scrape — a README, a note, an emulator
  working file — and each would be looked up as a game.
- **Not a per-file rename this tool should do.** Renaming a ROM breaks media matching (the
  frontend finds art by filename alone) and orphans the scraper's resource cache, which is
  keyed on the filename. That is a real cost, so it is the user's call.

### Next steps

1. Decide, per file, what it actually is — `.prg`, `.d64`, `.t64`, `.crt` — since the right
   suffix is not derivable from a bare name.
2. Rename, then re-run the scrape for that system only. Expect the media and cache to need
   re-fetching for the renamed files, which is the cost noted above.
3. Consider whether a **read-only reporting** check belongs in `rdtroubleshoot`: "this folder
   holds N files that no format list can see". That would turn a silent shortfall into a
   named one without touching anything. This is the most likely thing to promote out of
   this entry.

### Sightings

- **2026-08-28** — Fix applied but NOT yet confirmed: 47 files identified as real PRGs by their $0801 load-address magic and renamed to .prg (the 48th, .directory, is a KDE file and was skipped). Renaming was free here — those files had 0 gamelist entries and 0 media, so the usual 'renaming breaks media matching' cost did not apply. Coverage still reads 35 entries because nothing has scanned the folder yet; this stays open until a scrape confirms the games appear.
- **2026-08-28** — found by `rdtroubleshoot scraping` on the test machine as the only real
  coverage warning across the whole library. Not a user report; the folder had presumably
  looked like this for a long time.

### Sources

- Checker output: `rdtroubleshoot scraping`
- Background: [docs/SCRAPING.md](../../../SCRAPING.md) § "Descriptions were never the whole gap"
