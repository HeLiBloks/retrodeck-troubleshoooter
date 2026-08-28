---
slug: zero-byte-asset-stub-fatal-error
area: emulation
status: open
first_seen: 2026-08-28
last_confirmed: 2026-08-28
signatures:
  - source: symptom
    pattern: (worked|ran|played|fine) (for a while|a bit|a few minutes).*(then|before) (crash|error|hang|freez|quit)
    note: launches and plays, then dies at a repeatable point rather than at startup
  - source: symptom
    pattern: (error|fatal).*(dialog|box|window).*(exit|debug).*(game|window) (still|stays) open
    note: an engine's own assert dialog, with the game window alive behind it
  - source: retrodeck-log
    pattern: (invalid fps of zero|has no frames|failed to (load|parse)|malformed|corrupt(ed)? (file|asset|animation|texture))
    note: engine-assert language for an asset it could open and could not use; the engine usually names the file in the same line, and that filename identifies the screen being entered
  - source: retrodeck-log
    pattern: \.(ani|anm|bik|ogg|png|dds|pcx|wav|vp|pk3|pak)\)?[^\n]{0,60}(invalid|malformed|corrupt|no frames|zero)
    note: the same failure with the filename printed first, which is the order most engines use
  - source: retrodeck-log
    pattern: File: [a-z_0-9]+\.cpp
    note: the second line of a typical C++ engine assert block, useful when the message itself is truncated
---

# A game launches fine, then dies at one repeatable point — a 0-byte asset stub

## TL;DR

We have seen this and the fix is **applied but not yet confirmed by a playthrough**.
A game that starts, plays, and then dies whenever it reaches a particular screen is usually
choking on **one asset**, and the worst kind is a file that exists but is empty. Engines
almost always treat a *missing* asset as normal and an *unparseable* one as fatal, so a
0-byte stub is the one state that crashes. Find them with `find . -type f -size 0`, **move**
them out of the game tree rather than deleting, and the engine falls back to its
missing-file path. Do not reinstall over it — the rest of the install is probably fine.

---

## Engineer notes

### Symptom signature

An engine assert, offering no way to continue:

```
Error: animation (cb_train-01_a.ani) has invalid fps of zero, fix this!
File: generic.cpp
Line: 298
```

Other tells:

- **The game window stays open behind the dialog**, so the user reports a hang, not a crash.
- It fires on *entering a screen*, not at startup — so the game launches, the menus work,
  and the failure arrives minutes later. This is what makes it feel intermittent when it is
  perfectly deterministic.
- The filename in the message names which screen was being entered.

### What is known

**Why an empty file is worse than an absent one.** Engines distinguish the two, and the
distinction is the whole diagnosis. From the worked example's source
(`code/graphics/generic.cpp` in FreeSpace Open):

- a **missing** file fails the lookup and takes a graceful `return -1`;
- a file that **exists and parses to zero** reaches
  `Error(LOCATION, "animation (%s) has invalid fps of zero, fix this!")`, which is fatal.

A 0-byte file is *found*, so it takes the fatal path. Read the engine's source for the exact
message before assuming — it takes one search and it converts a guess into a mechanism.

**How to find them.** One command over the game tree, and the result is usually stark:

```sh
find . -type f -size 0 | wc -l
find . -type f -size 0 -printf '%h\n' | sort | uniq -c | sort -rn
```

On the worked example: 67 empty files out of 5557, confined entirely to two asset
directories, with every other loose file intact.

**The archive trap, which is what makes this hard to see.** An install can be stripped by
gutting its archives, and **an archive stripped to its index still lists every original
filename at its original size**. So "is the file in the pack?" answers *yes* for data that
is not there. Compare the highest `offset + size` any index entry claims against the
archive's real length instead:

```
root_fs2.vp        file=  6404494  files= 160  data_needs=   6396926  OK
sparky_fs2.vp      file=   134612  files=3037  data_needs= 260428856  INDEX ONLY - DATA ABSENT
tango1_fs2.vp      file=     1600  files=  32  data_needs= 195885649  INDEX ONLY - DATA ABSENT
```

Seven of eight packs there were hollow; the game had been running off a loose extracted tree
the whole time. The same shape applies to any indexed container — the index is cheap to keep
and the payload is what gets stripped.

**Turn that index into an audit.** Because it survives, it is a manifest of what a complete
install contains. Classify every entry as in-pack / loose-and-good / loose-but-empty /
missing and the gap is exact:

```
  5424  loose ok
   185  in pack
    67  loose EMPTY    <- the crash
     2  MISSING        <- two interface sounds, harmless
```

That is what turns "the install might be broken" into "these 67 files, and nothing else".

### What has been ruled out

- **Not a bad engine build or version.** The same binary launches and renders other screens
  from the same data repeatedly. The failure is data-driven and confined to one file class.
- **Not recoverable from the archives**, when they are hollow. Verified by parsing them.
- **Not a reason to reinstall.** The audit showed the install otherwise complete — missions,
  models, voice, interface, maps all present. Wiping it to "start clean" would have
  destroyed a working install to fix 67 empty files.

### Next steps

1. **Confirm by playing** to the point that failed before. This is the outstanding step and
   it needs a human — see *Verification* below for why automation runs out here.
2. If confirmed, promote this entry.
3. If the assets are wanted back, copy the affected directories from an original install of
   the game. Losing decorative assets usually costs presentation only; check what the
   directory actually holds before assuming that.

### The fix applied, pending that confirmation

**Move, do not delete.** A 0-byte file has no content to lose, which is the entire safety
argument for the step — and re-checking each file for being genuinely empty *at the moment
it is moved* is what keeps that argument true if the tree changed since the survey:

```sh
game="<game root>"
quar="<somewhere outside the game root>/empty-asset-stubs-<date>"
cd "$game"
while IFS= read -r f; do
    [[ -s "$f" ]] && { echo "REFUSED (not empty): $f"; continue; }
    mkdir -p "$quar/$(dirname "$f")"
    mv "$f" "$quar/$f"
done < <(find . -type f -size 0 -print)
```

**Put the quarantine outside the directory the engine treats as its data root**, or it will
simply find the stubs again. A sibling of the game root is enough. Check too that the
quarantine does not land somewhere the frontend scans for games.

Confirmed afterwards on the worked example: no 0-byte file anywhere in the tree; the audit
reclassifies all 67 from `loose EMPTY` to `MISSING`; and the game still launches through the
RetroDECK sandbox to its profile screen with no stderr output and no error window.

### Verification

The confirming test is reaching the screen that failed. See
[`../../../DRIVING-A-GAME-GUI.md`](../../../DRIVING-A-GAME-GUI.md) for driving a game's menus
from an SSH session, and for the two limits that bit this case:

- the engine took **relative mouse input**, so absolute pointer moves could work its menus
  but not its gameplay;
- its "jump straight to this level" flag **skipped the briefing**, which is exactly the
  screen that fails — a reproduction route that silently avoids the bug.

Both are the same lesson: **absence of a symptom under conditions that cannot trigger it is
not evidence.** This entry stays in `backlog/` until somebody plays through the failing
screen.

### Sightings

<!-- Newest first. `rdtroubleshoot kb sighting zero-byte-asset-stub-fatal-error "..."` appends here and moves
     last_confirmed forward. A second sighting is the cue to investigate and promote. -->

- **2026-08-28** — FreeSpace 2 under FreeSpace Open, hit twice in one session. First by a
  diagnostic run against a brand-new profile, where it was **wrongly written off as a
  non-reproducing one-off**; then by the user in normal play, who caught the dialog in a
  screenshot. The bad call came from declaring it non-reproducing on the strength of an idle
  run, a relaunch and a `SIGTERM` — none of which load an asset of that kind. The trigger was
  never identified, and "did not recur" was read as "was not real".

### Sources

- A screenshot of the engine's error dialog — often the fastest complete evidence there is
- The engine's own source for the message, to establish missing-vs-malformed handling
- `find <game root> -type f -size 0`
- An archive-integrity pass comparing `max(offset + size)` against each container's length
