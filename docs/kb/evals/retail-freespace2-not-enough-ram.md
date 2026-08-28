---
slug: retail-freespace2-not-enough-ram
kb_entry: ../errors/emulation/retail-freespace2-not-enough-ram.md
recorded: 2026-08-28
verified_by: the FS2 main hall and then the Choose Pilot screen rendered from the retail .vp data, screenshotted from a launch made through the RetroDECK sandbox, with no Not Enough RAM window on the X server and a clean exit leaving no flatpak-spawn/bwrap/engine processes
sources:
  - kind: log
    path: ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
  - kind: window-list
    command: xwininfo -root -tree
---

# Eval fixture — retail-freespace2-not-enough-ram

A recorded case that this entry's diagnosis must keep getting right. Two purposes: it is
the stable record of what the problem actually looked like, and it is a regression check —
replay the input and confirm the diagnosis still lands.

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

## Expected — diagnosis anchor

- **Match:** `retail-freespace2-not-enough-ram` via signature
  `retrodeck-log: Proton: Upgrading prefix from None to [\d.\-]+ \([^)]*freespace2-proton`
- **Diagnosis:** the retail 1999 `FS2.exe` misreports available memory on a large-RAM host
  and refuses to start, before any renderer is initialised. Not a graphics, prefix, sandbox
  or permissions problem.
- **Lead action:** run the FreeSpace Open engine against the retail `.vp` data instead, with
  the launcher's working directory set to the folder holding those files.

## Notes

Three things make this a fixture worth keeping.

**The log looks healthy.** There is no `[ERROR]`, no non-zero exit, and ES-DE records 83
seconds of play time and updates the gamelist — that 83 seconds is really the user reading
a modal dialog. Any diagnosis that starts by grepping for error lines finds nothing here and
concludes the launch worked. The routable signal is the *absence* of anything after the two
Proton lines, plus `Upgrading prefix from None` recurring on every launch.

**There are three red herrings, and all three had already been chased** before this was
filed: the wrong executable (`freespace2.exe` is the config tool, `FS2.exe` is the game —
both fail identically), the Proton prefix, and the DirectDraw/Direct3D renderer registry
keys. Each is a plausible cause for "old Windows game will not start", and each is ruled out
by the single fact that the memory check runs before renderer selection.

**Reproducing it needs `XAUTHORITY`.** Running the launcher over SSH without it exits 0 with
`Authorization required, but no authorization protocol specified` and never draws the
dialog — a *different* failure that looks like the same one. The fixture is only valid if
the reproduction is done against the seated session's `/run/user/<uid>/xauth_*`. This is the
same shape as the `PATH`-test near-miss recorded in `skyscraper-not-on-path`: a test run in
the wrong environment confirms the wrong thing.
