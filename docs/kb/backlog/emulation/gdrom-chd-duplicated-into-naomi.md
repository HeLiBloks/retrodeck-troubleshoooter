---
slug: gdrom-chd-duplicated-into-naomi
area: emulation
status: open
first_seen: 2026-08-28
last_confirmed: 2026-08-28
signatures:
  - source: symptom
    pattern: (arcade|naomi).*(listed twice|duplicate|won'?t (open|launch)|blank entry)
    note: the same game appears twice in one system, and one of the two does nothing
  - source: retrodeck-log
    pattern: extension is not configured in es_systems\.xml
    note: ES-DE lists the entry and refuses to open it; logged once per entry per startup
  - source: retrodeck-log
    pattern: Couldn't process "[^"]*\.chd", skipping entry
    note: the second line ES-DE logs for the same entry
  - source: checker
    pattern: Dead gamelist entries
---

# GD-ROM discs duplicated into the naomi folder — unopenable gamelist entries and gigabytes of identical files

## TL;DR

We have seen this and there is **no fix recorded yet**, because the remedy means deleting
ROMs and that is the library owner's decision. The GD-ROM set exists **twice** — under both
`roms/naomi/` and `roms/naomigd/`, byte-for-byte identical — and the `naomi` copy also puts
**57 disc images into `naomi/gamelist.xml` as if they were games**. ES-DE lists those 57 and
cannot open any of them, so each affected title appears twice in that system with one of the
two doing nothing. Nothing is broken or at risk; the working `.zip` entry still launches.

---

## Engineer notes

### Symptom signature

Two lines per affected entry, on every ES-DE startup:

```
[WARN] [ES-DE] File "/roms/naomi/cvs2/gdl-0007a.chd" is present in gamelist.xml but the extension is not configured in es_systems.xml
[WARN] [ES-DE] Couldn't process "/roms/naomi/cvs2/gdl-0007a.chd", skipping entry
```

Other tells:

- 114 of one log's 124 `[WARN]` lines were these two classes — 57 entries × 2.
- In the frontend, an affected title shows **twice** in `naomi`: once from its `.zip`
  (works) and once from its `.chd` (does nothing).
- **Both entries are scraped**, with the same `<name>`, so it does not look like a stray
  file — it looks like a deliberate duplicate.

### What is known

Measured on the test machine, 2026-08-28:

- **The `naomi` system does not declare `.chd`.** Its extension list is
  `.bin .dat .elf .lst .7z .zip` — and so is `naomigd`'s and `naomi2`'s. Only `neogeocd`
  declares `.chd`. So ES-DE is behaving correctly: it will not open a file whose extension
  the system does not list.
- **A GD-ROM game is a `.zip` plus a companion `.chd`**, not two games. The romset zip is
  the entry point and the emulator finds the disc image beside it. Every one of the 47
  CHD-bearing directories under `naomi/` has a matching top-level `.zip`, and `naomigd`
  models this correctly: 48 gamelist entries, all `.zip`, and **zero** of its 54 CHDs are
  listed. That is why `naomigd` produces no warnings at all.
- **The duplication is exact, not approximate.** All 48 of `naomigd`'s top-level `.zip`
  stems are also in `naomi`, and 45 of `naomi`'s 47 CHD directories are also in `naomigd`.
  MD5 on a sampled pair matches on both halves:
  ```
  5cd45c5f9b5af283c63690dcfe4116ee  naomi/azumanga/gdl-0018.chd
  5cd45c5f9b5af283c63690dcfe4116ee  naomigd/azumanga/gdl-0018.chd
  0d14249257477537186da517ecc459c4  naomi/azumanga.zip
  0d14249257477537186da517ecc459c4  naomigd/azumanga.zip
  ```
- **Cost of the `naomi` copy: 7.25 GiB** — 6.88 GiB of CHDs plus 0.37 GiB of romset zips.
- Worked example of the triple listing: *Azumanga Daioh Puzzle Bobble* appears **twice** in
  `naomi/gamelist.xml` (as `azumanga/gdl-0018.chd` and as `azumanga.zip`) and **once** in
  `naomigd/gamelist.xml`.

### What has been ruled out

- **Not an ES-DE bug and not a broken dump.** The files are intact, and refusing an
  extension the system does not declare is correct behaviour.
- **Not a scraper fault.** The scraper matched these correctly — that is *why* the `.chd`
  entries carry real titles and descriptions. It filled in entries that should not have
  been in the gamelist in the first place.
- **Not fixable by adding `.chd` to `naomi`'s extension list**, which is the obvious-looking
  move and is wrong: it would turn 57 refused entries into 57 *accepted* duplicate games,
  each shadowing a working `.zip` entry. The dead entries are the symptom; the duplication
  is the cause.
- **Not the same as [c64-roms-without-extension-invisible](c64-roms-without-extension-invisible.md)**,
  despite both being about extensions. There, files have **no** extension and are never
  seen at all; here they have one the system does not declare and are seen, listed and
  refused. Opposite direction, different fix.

### Next steps

The library owner has to choose, because every route deletes something:

1. **Remove the 57 spurious `.chd` entries from `naomi/gamelist.xml`** and leave every file
   alone. Lowest risk: it deletes no ROM, ends 114 warnings per startup, and removes the
   duplicate listings. Requires RetroDECK closed (ES-DE rewrites gamelists on exit) and a
   gamelist backup, which the rotation already takes.
2. **Also remove the duplicated GD-ROM files from `naomi/`**, reclaiming 7.25 GiB, on the
   reasoning that `naomigd` is the system that exists for GD-ROM and already holds an
   identical copy. **This needs confirming before acting** — verify the full set by hash
   rather than by the sampled pair, and check that no launcher or per-game config in the
   `naomi` system points at those paths.
3. **Do nothing.** It costs 7.25 GiB and some log noise, and no game is unplayable.

**Two safety notes for whoever acts on this.** `keyboard` and `luptype` are CHD directories
present **only** under `naomi/` — they are *not* duplicated, so a blanket delete of
`naomi/*/` would lose them. And option 2 must be verified against the whole set: 45 of 47
directories overlap, and the two that do not are exactly the ones a careless glob would take.

### Sightings

- **2026-08-28** — found by reading the log rather than from a report, while checking why
  `rdtroubleshoot emulation` said the log was clean. It was not: the checker read only
  Ryujinx's `|E|` format and never ES-DE's `[WARN]`, so 124 warnings were invisible. That
  blindness is fixed; this entry is what the fix surfaced.

### Sources

- Log excerpt: `~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log`
- Checker output: `rdtroubleshoot emulation` — `Dead gamelist entries`
- System definitions: ES-DE's shipped `es_systems.xml` (naomi/naomigd/naomi2/neogeocd)
