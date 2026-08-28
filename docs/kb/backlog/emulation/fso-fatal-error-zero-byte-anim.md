---
slug: fso-fatal-error-zero-byte-anim
area: emulation
status: open
first_seen: 2026-08-28
last_confirmed: 2026-08-28
signatures:
  - source: symptom
    pattern: (freespace|fs2).*(error!|invalid fps|stopped working|hangs? (on|at) (a )?brief)
    note: an Error! dialog offering only Exit and Debug, with the game window still open behind it
  - source: retrodeck-log
    pattern: animation \([^)]+\.ani\) has invalid fps of zero
    note: FSO writes this to stderr, which ES-DE captures as the launched game's output; the filename in the parentheses names the screen that was being entered
  - source: retrodeck-log
    pattern: File: generic\.cpp
    note: the second line of the same FSO Error block, useful when the first is truncated
---

# FreeSpace Open raises a fatal "invalid fps of zero" Error on a briefing

## TL;DR

We have seen this and the fix is **applied but not yet confirmed by a playthrough**. The
cause is established: the install's animation files are **0-byte stubs**, and FSO treats a
file that exists-but-parses-to-0-fps as a fatal error while treating an *absent* one as
normal. Moving the empty stubs out of the game tree should turn the crash into a briefing
that simply plays without its animation. Do not delete the retail data to "reinstall
cleanly" — the rest of this install is complete and the animations are not recoverable from
the packs.

---

## Engineer notes

### Symptom signature

A dialog titled `Error!` with only **Exit** and **Debug** — no "continue":

```
Error: animation (cb_train-01_a.ani) has invalid fps of zero, fix this!
File: generic.cpp
Line: 298
```

Other tells:

- **The game window stays open behind the dialog**, so it presents as a hang rather than a
  crash. The user's description was "it worked for a while and then crashed".
- It fires on entering a screen that plays an animation — a command briefing
  (`cb_*.ani`) or the tech room's intel display (`intel_*.ani`) — not at startup. So the
  game launches, the main hall works, and the failure comes minutes later.
- The filename in the parentheses names which screen was being entered.

### What is known

Measured on the machine, 2026-08-28:

- **Every animation in the install is 0 bytes** — 67 files, and they are the *only* empty
  files in the tree:

  | directory | empty files |
  |---|---|
  | `data/cbanims` | 57 |
  | `data/intelanims` | 10 |

- **Why an empty file is fatal but a missing one is not**, from FSO's own source
  (`code/graphics/generic.cpp`, `generic_anim_stream()`):
  - a missing file fails `cf_find_file_location_ext` and takes a graceful `return -1`;
  - a file that exists and parses to 0 fps reaches
    `Error(LOCATION, "animation (%s) has invalid fps of zero, fix this!")`, which is fatal.

  A 0-byte file is *found*, so it takes the fatal path. This is the whole mechanism, and it
  is why removing the stub is a fix rather than a workaround.

- **Seven of the eight `.vp` packs are index-only stubs.** They list every original filename
  at its original size and contain none of the bytes:

  ```
  root_fs2.vp        file=  6404494  files= 160  data_needs=   6396926  OK
  sparky_fs2.vp      file=   134612  files=3037  data_needs= 260428856  INDEX ONLY - DATA ABSENT
  tango1_fs2.vp      file=     1600  files=  32  data_needs= 195885649  INDEX ONLY - DATA ABSENT
  ```

  The game runs off the loose extracted `data/` tree instead. **This is a trap worth naming:
  a "is the file in a `.vp`?" check answers *yes* for data that is not there**, because the
  directory index survives the stripping. Compare the highest `offset + size` any index
  entry claims against the pack's real length instead.

- **Using those indexes as a manifest, the install is otherwise complete:**

  ```
    5424  loose ok
     185  in pack
      67  loose EMPTY    <- the animations
       2  MISSING        <- SWITCH.WAV, L_FAIL.WAV (interface sounds, harmless)
  ```

  Missions, models, voice, interface and maps are all present. The animations were stripped
  to save space — they are the largest files by far (`intel_ancients.ani` is 28 MB when
  complete; the 67 together are roughly a gigabyte).

### What has been ruled out

- **Not a bad FSO build or version.** The same binary launches, renders the main hall from
  this data, and reaches Choose Pilot repeatedly. The failure is data-driven and specific to
  one file class.
- **Not recoverable from the `.vp` packs.** They hold the index only; the animation bytes
  are not on the machine. Verified by parsing every pack.
- **Not available elsewhere on the box.** No other FreeSpace install, no `*_fs2.vp` over
  1 MB anywhere on the filesystem, and FS2 is not in the Steam library.
- **Not related to the earlier
  [retail-freespace2-not-enough-ram](../../errors/emulation/retail-freespace2-not-enough-ram.md)
  fault**, though it is the same game and the same afternoon. That one was the retail
  executable refusing to start at all; this one is the FSO engine failing on data, after a
  successful launch. Treating the second as a regression of the first would be wrong.

### Next steps

1. **Confirm by playing** to the point that failed before — a command briefing. This is the
   only outstanding step, and it needs a human: FSO takes relative mouse input so its menus
   cannot be driven reliably over SSH, and `-start_mission` skips briefings, so neither
   route exercises the path.
2. If it is confirmed, promote this entry.
3. If the animations are wanted back, copy `data/cbanims/` and `data/intelanims/` from an
   original FreeSpace 2 install into the game directory. Losing them costs presentation
   only — no gameplay depends on them.

### The fix applied, pending that confirmation

The 67 empty stubs were **moved, not deleted**, to a dated directory that is a *sibling* of
the game root rather than inside it, so FSO cannot see it:

```sh
game="$HOME/retrodeck/roms/ports/FreeSpace 2/FS2"
quar="$HOME/retrodeck/roms/ports/FreeSpace 2/empty-anim-stubs-20260828"
cd "$game"
while IFS= read -r f; do
    [[ -s "$f" ]] && { echo "REFUSED (not empty): $f"; continue; }
    mkdir -p "$quar/$(dirname "$f")"
    mv "$f" "$quar/$f"
done < <(find data -type f -size 0 -print)
```

Re-checking each file for being genuinely empty *at the moment it is moved* is the point:
a 0-byte file has no content to lose, and that is the entire safety argument for the step.
67 moved, 0 refused.

What was confirmed afterwards: no 0-byte file remains anywhere in the game tree; the audit
reclassifies all 67 from `loose EMPTY` to `MISSING`; and the game still launches through the
RetroDECK sandbox to Choose Pilot with no stderr output and no `Error!` window.

### Sightings

<!-- Newest first. `rdtroubleshoot kb sighting fso-fatal-error-zero-byte-anim "..."` appends here and moves
     last_confirmed forward. A second sighting is the cue to investigate and promote. -->

- **2026-08-28** — hit twice in one session on the same machine. First by a diagnostic run
  against a brand-new pilot, where it was wrongly written off as a non-reproducing one-off;
  then by the user in normal play, who captured the dialog as a screenshot. The first call
  was wrong because the trigger was never identified — "did not recur" was read as "was not
  real", when the truth was that the idle main hall simply never loads an animation.

### Sources

- Screenshot of the `Error!` dialog, 2026-08-28 20:01
- `code/graphics/generic.cpp` in the FSO release this box runs (26.0.0)
- Pack audit: parse each `.vp` header and compare `max(offset + size)` with the file length
