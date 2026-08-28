---
slug: old-game-fails-its-own-startup-check
kb_entry: ../errors/emulation/old-game-fails-its-own-startup-check.md
recorded: 2026-08-28
verified_by: on the worked example (FreeSpace 2), replacing the retail executable with the FreeSpace Open engine produced the game's own main hall and pilot-select screen rendered from the retail data, screenshotted from a launch made through the RetroDECK sandbox, with the refusal dialog absent from the X window list and a clean exit leaving no flatpak-spawn/bwrap/engine processes
sources:
  - kind: log
    path: ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
  - kind: window-list
    command: xwininfo -root -tree
---

# Eval fixture — old-game-fails-its-own-startup-check

A recorded case that this entry's diagnosis must keep getting right. Two purposes: it is
the stable record of what the problem actually looked like, and it is a regression check —
replay the input and confirm the diagnosis still lands.

The case is FreeSpace 2, but the entry is about the class. A good diagnosis here should
reach "the game's own startup check is refusing, replace the executable with an engine"
without needing to know the title.

## Input — verbatim evidence

The user's description:

> Launching the FreeSpace 2 port through ES-DE/RetroDECK opens a dialog: "FreeSpace has
> detected that you only have 0MB of free memory. FreeSpace requires at least 32MB of
> memory to run." Pressing OK causes the game to exit.

The RetroDECK log for that launch — note that it contains **no error line**:

```
[2026-08-28 19:23:46.845] [INFO] [ES-DE] Launching game "FreeSpace 2" from system "Ports (ports)"...
[2026-08-28 19:23:46.845] [DEBUG] [ES-DE] FileData::launchGame(): Using default emulator "Script"
[2026-08-28 19:23:46.848] [INFO] [ES-DE] /usr/bin/bash /home/<user>/retrodeck/roms/ports/FreeSpace\ 2.sh
[2026-08-28 19:25:09.807] [DEBUG] [ES-DE] Output from launched game:
Proton: Upgrading prefix from None to 11.0-100 (/var/home/<user>/retrodeck/saves/freespace2-proton/)
ntsync: up and running.
[2026-08-28 19:25:09.807] [DEBUG] [ES-DE] FileData::setPlayMetadata(): Play time was 83 seconds
```

The confirming evidence, from the live X server while the game was blocked:

```
0x2600001 "Not Enough RAM": ("steam_proton" "steam_proton")  280x154+820+453
```

And the host's actual memory at that moment: 47527 MB total, 40407 MB available.

## Expected — diagnosis anchor

- **Match:** `old-game-fails-its-own-startup-check` via signature
  `retrodeck-log: Proton: Upgrading prefix from None to`
- **Diagnosis:** the game's own startup check misjudges the host and refuses to run, before
  any renderer is initialised. Not a graphics, prefix, sandbox or permissions problem.
- **Lead action:** find a community engine or source port that reads the original game data
  and point the launcher at it, with the working directory on the data.

## Notes

Four things make this a fixture worth keeping.

**The log looks healthy.** There is no `[ERROR]`, no non-zero exit, and ES-DE records 83
seconds of play time and updates the gamelist — that 83 seconds is really the user reading a
modal dialog. Any diagnosis that begins by grepping for error lines finds nothing and
concludes the launch worked. The routable signal is the *absence* of anything after the two
runtime lines, plus `Upgrading prefix from None` recurring on every launch.

**There are three red herrings, and all three had already been chased** before this was
filed: the wrong executable (a configuration launcher shipped beside the game binary), the
compatibility prefix, and the renderer registry keys. Each is a plausible cause for "old
Windows game will not start", and each is ruled out by the single fact that the check runs
before renderer selection. A diagnosis that proposes any of them has failed this fixture
even if it sounds reasonable.

**Reproducing it needs `XAUTHORITY`.** Running the launcher over SSH without it exits 0 with
`Authorization required, but no authorization protocol specified` and never draws the
dialog — a *different* failure that looks like the same one. The fixture is only valid if
the reproduction runs against the seated session's `/run/user/<uid>/xauth_*`. Same shape as
the `PATH`-test near-miss in `skyscraper-not-on-path`: a test run in the wrong environment
confirms the wrong thing.

**The window title carried the answer.** `xwininfo -root -tree` produced the diagnosis in
one line after three sessions had guessed at the graphics path. A fixture that rewards
looking at the window list before the log is worth keeping for that alone.
