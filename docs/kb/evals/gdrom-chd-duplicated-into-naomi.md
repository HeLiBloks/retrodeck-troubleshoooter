---
slug: gdrom-chd-duplicated-into-naomi
kb_entry: ../errors/emulation/gdrom-chd-duplicated-into-naomi.md
recorded: 2026-08-28
verified_by: 104 files re-hashed identical at deletion, 7.25 GiB freed, 0 play history lost
sources:
  - kind: log
    path: ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
  - kind: checker
    command: rdtroubleshoot emulation
---

# Eval fixture — gdrom-chd-duplicated-into-naomi

## Input — verbatim evidence

Two lines per affected entry, on every startup:

```
[WARN] [ES-DE] File "/roms/naomi/cvs2/gdl-0007a.chd" is present in gamelist.xml but the extension is not configured in es_systems.xml
[WARN] [ES-DE] Couldn't process "/roms/naomi/cvs2/gdl-0007a.chd", skipping entry
```

The checker's summary of the same:

```
WARN  Dead gamelist entries  57 entries are in a gamelist with an extension the system does
                             not declare, so ES-DE lists them and cannot open them —
                             system(s): naomi, neogeocd
```

## Expected — diagnosis anchor

- **Match:** `gdrom-chd-duplicated-into-naomi` via signature
  `retrodeck-log: extension is not configured in es_systems\.xml`
- **Diagnosis:** the GD-ROM set was copied into `naomi/` as well as `naomigd/`, and the
  `naomi` copy's disc images were scraped into its gamelist as if they were games. A GD-ROM
  game is a `.zip` plus a companion `.chd`, not two games.
- **Lead action:** establish which side has the play history, remove the duplicate and
  unopenable entries from the redundant side, then delete its files with a hash check at the
  moment of deletion.

## Notes

Three near-misses this fixture exists to guard against.

**The obvious fix is backwards.** `naomi` does not declare `.chd`, so adding it to the
extension list looks like the fix. It would convert 57 *refused* entries into 57 *accepted*
duplicates, each shadowing a working `.zip`. The dead entries are the symptom; the
duplication is the cause.

**"Which system ought to own GD-ROM" is not evidence.** It happened to give the right answer
here, but the thing that actually settles it is `playcount`/`favorite`: all 45 plays and 6
favourites on the `naomi` side belonged to titles that are *not* duplicated, and `naomigd`
had 19. Had the numbers fallen the other way, the correct action reverses — and reasoning
from system names would have deleted the copy in use.

**A blanket glob is wrong even when the diagnosis is right.** 45 of 47 CHD directories
overlapped; `keyboard` and `luptype` existed only under `naomi/` and are exactly what
`rm -rf naomi/*/` takes.
