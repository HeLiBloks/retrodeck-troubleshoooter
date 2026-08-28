---
slug: gdrom-chd-duplicated-into-naomi
area: emulation
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: 104 files re-hashed identical at the moment of deletion, 7.25 GiB freed, 104 gamelist entries removed with 0 playcount/favourite lost, both gamelists re-parse, keyboard/luptype asserted surviving
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

The GD-ROM set exists **twice** — under `roms/naomi/` and `roms/naomigd/` — and the `naomi`
copy also lists its disc images in `naomi/gamelist.xml` as if they were games, which ES-DE
lists and cannot open. **`naomigd` is the system that exists for GD-ROM; the `naomi` copy is
dead weight.** Remove the duplicate and unopenable entries from `naomi/gamelist.xml`, then
delete the duplicated files from `naomi/` — but **hash-verify every file first**, and check
play history before removing any entry. On the machine this was found on that reclaimed
7.25 GiB and ended 114 warnings per startup, with no play history lost.

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

### Fix

**Establish which side is canonical before touching anything**, by play history rather than
by reasoning about which system *ought* to own GD-ROM. `playcount` and `favorite` live in
the gamelist and are the only record of what the user actually plays:

```sh
# per system: entries, how many played, how many favourited
```

On the machine this was found on the answer was unambiguous: of `naomi`'s 45 played games
and 6 favourites, **every one belonged to a title that is not duplicated**. The 48
duplicated `.zip` entries and 56 `.chd` entries had **0 plays and 0 favourites**, while
`naomigd` had 19 plays. So GD-ROM games were only ever launched from `naomigd`.

Then, in this order:

1. **Close RetroDECK.** ES-DE rewrites every gamelist on exit, so a gamelist edited while it
   runs is discarded and the write reports success.
2. **Back up the gamelists** you are about to touch.
3. **Remove the unopenable and duplicate entries**, skipping any entry that carries a
   `playcount` or `favorite` whatever the rule says — history is never worth reclaiming
   space for.
4. **Delete the duplicated files, re-hashing each at the moment of deletion.** Not from an
   earlier survey: a file may have changed between the survey and the delete, and the whole
   safety of this step is that the twin is identical. Refuse any file whose twin does not
   match rather than deleting it anyway.
5. **Protect the directories that exist on one side only.** Here they were `keyboard` and
   `luptype` — 45 of 47 CHD directories overlapped, and the two that did not are exactly
   what a `naomi/*/` glob would have taken. Assert they survive afterwards.
6. **Orphaned media**: the removed entries leave their artwork behind (403 MiB here). Move
   it to a dated directory rather than deleting it — it is regenerable but only at the cost
   of a scrape, and `naomigd` already has its own copy.

### Verification

Measured on the machine, after the fix:

- `naomi/gamelist.xml`: **196 → 92 entries** — 56 `.chd` and 48 duplicates removed, **0
  skipped for history** because none had any.
- Files: **104 re-hashed identical at the moment of deletion, 0 refused, 7.25 GiB freed**;
  the ROM volume went from 715.8 to 721 GiB free.
- `naomigd` **untouched**: 48 zips and 45 CHD directories before and after.
- `keyboard` and `luptype` asserted present afterwards.
- Both edited gamelists re-parse.
- `rdtroubleshoot emulation` exits **0**, and reports the log's 57-entry complaint as
  **stale** — the log still holds the run that predates the fix. Launch RetroDECK once for
  the final confirmation that the warnings stop.

### Generalising it: the same sweep over the whole ROM tree

Worth doing once, because this was one instance of a pattern. Group every file by size,
hash only the groups that collide, and the cost stays trivial — on a 154 GiB tree with
25,983 files that was 49 candidate groups and 5.7 GiB to hash, finding **27 true duplicate
groups / 2.55 GiB**. Then the same play-history gate decides each one, and it does **not**
give the same answer everywhere:

| duplicate | verdict |
|---|---|
| A disc image listed as a game beside its own romset | **remove** — unopenable, and the romset already covers it |
| One game under two filenames, both unplayed | **remove one** — a real duplicate |
| An arcade romset in both a dedicated system and a full MAME set | **keep both** — see below |
| Two MAME romset *names* sharing content | **never touch** — see below |

**Keep an arcade romset that appears in both a dedicated folder and a full MAME set.**
Found 20 such groups (14 atomiswave↔mame, 6 model2↔mame, ~1.7 GiB). This looks identical to
the GD-ROM case and is not, for three reasons: both copies are **fully functional** where
naomi's `.chd` entries could not open at all; a MAME set is curated as a *set*, so deleting
members makes it incomplete and any future set update restores them; and the play history
shows **both** sides in use — the dedicated folders had 19 plays and a favourite, but
`demofist` had been played from `mame`. The duplication is the honest cost of keeping a
complete MAME set alongside per-platform folders, which is a legitimate library structure.

**Never delete one of two MAME romset names that share content.** A romset filename is a
machine code, not a title: `kizuna`/`kizuna4p`, `3do`/`3dobios`, `gz70sp`/`wg130`,
`a2000`/`a500` all hold identical bytes and MAME requires **each under its own name** —
deleting either breaks that machine. This is the same trap as stripping a version suffix
from a romset name, and a hash match is precisely the evidence that makes it look safe.

### When this entry does not fit

- **Play history exists on the side you were about to delete.** Then that side is the one in
  use and the diagnosis reverses. Check before acting, every time.
- The two copies are **not** hash-identical — then they are different dumps, not duplicates,
  and deleting either loses something.
- The unopenable entries are in a system that has **no** counterpart holding the same games.
  Then removing the entries is still right, but there is nothing to reclaim and the files
  must stay.

### Sightings

- **2026-08-28** — Swept the whole ROM tree for the same pattern: 25983 files / 154 GiB reduced to 49 size-collision groups, hashing 5.7 GiB, giving 27 true duplicate groups / 2.55 GiB. Acted on two: dreamcast 'Sonic Adventure (USA) (Rev A).chd' (871 MiB, byte-identical to the (EnJaFrDeEs) copy, both unplayed) and amigacd32 'myth_history_in_making_v1.0' (a typo of 'in_the_making'), 874 MiB total, re-hashed at deletion, media quarantined. Deliberately kept the 20 arcade groups duplicated between atomiswave/model2 and the full MAME set (~1.7 GiB): both copies work, a MAME set is curated as a set, and demofist had been played from mame. Never touched the MAME romset name-pairs.
- **2026-08-28** — found by reading the log rather than from a report, while checking why
  `rdtroubleshoot emulation` said the log was clean. It was not: the checker read only
  Ryujinx's `|E|` format and never ES-DE's `[WARN]`, so 124 warnings were invisible. That
  blindness is fixed; this entry is what the fix surfaced.

### Sources

- Log excerpt: `~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log`
- Checker output: `rdtroubleshoot emulation` — `Dead gamelist entries`
- System definitions: ES-DE's shipped `es_systems.xml` (naomi/naomigd/naomi2/neogeocd)
