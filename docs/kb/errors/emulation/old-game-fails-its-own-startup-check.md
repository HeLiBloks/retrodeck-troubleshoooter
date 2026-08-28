---
slug: old-game-fails-its-own-startup-check
area: emulation
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: on the worked example (FreeSpace 2), replacing the retail executable with the FreeSpace Open engine produced the game's own main hall and pilot-select screen rendered from the retail data, screenshotted from a launch made through the RetroDECK sandbox, with the refusal dialog absent from the X window list and a clean exit leaving no flatpak-spawn/bwrap/engine processes
signatures:
  - source: symptom
    pattern: (won'?t|will not|does ?n'?t|refuses to) (start|launch|run).*(0\s*mb|not enough (ram|memory)|insufficient memory|requires at least|smartdrive|smartdrv)
    note: the game itself puts up a dialog blaming the machine, then exits when it is dismissed
  - source: symptom
    pattern: (old|retail|1990s|dos|win9x) game.*(dialog|popup|message box).*(exits?|quits?|closes?)
    note: the shape of the report, when the exact wording is not to hand
  - source: retrodeck-log
    pattern: Proton: Upgrading prefix from None to
    note: recurring on every launch of the same title means the prefix never completes a run - the app is dying early, and this is often the only trace in the log
---

# A pre-2000s game refuses to start, blaming the machine's memory or hardware

## TL;DR

**Stop trying to fix the environment and replace the executable.** When a 1990s game
inspects the host and refuses to start — "0MB of free memory", "requires at least 32MB",
a missing SmartDrive — the check runs *before* any renderer is chosen, so Proton versions,
DirectDraw/Direct3D registry keys, `PROTON_USE_WINED3D` and compatibility flags cannot
reach it. Look for a **community engine or source port** that reads the original game data,
point the port's launcher at that instead, and `cd` into the data directory first. The
original install stays untouched.

---

## Engineer notes

### Symptom signature

The game's own dialog, not the runtime's. Wording varies by title; the shape does not:

```
FreeSpace has detected that you only have 0MB of free memory.
FreeSpace requires at least 32MB of memory to run.
```

Confirm it is really this and not something dressed up as it, by finding the window on the
X server — the title is usually the whole diagnosis:

```
0x2600001 "Not Enough RAM": ("steam_proton" "steam_proton")  280x154+820+453
```

Other tells:

- **The wrapper exits 0 and leaves no process behind**, so nothing looks crashed.
- In the RetroDECK log the launch looks *successful*: there is no error line, only the
  launch and a couple of lines of runtime noise, plus a play time that is really the user
  reading a modal dialog.
- `Proton: Upgrading prefix from None` on **every** launch — the prefix is rebuilt each
  time because no run ever completes.

### What is known

The mechanism is a 32-bit era assumption meeting a machine far outside its range: a memory
or hardware query that cannot represent what a modern host reports, feeding a check that
concludes the machine is inadequate. Because that check is one of the first things the
program does, **everything downstream of it is irrelevant to the fault** — which is why the
graphics-side fixes that suggest themselves all fail.

Measured on the worked example below: 47527 MB total and 40407 MB available at the moment
the game claimed 0MB.

### What has been ruled out

For the worked example, and these generalise to the class:

- **Not the renderer.** Forcing WineD3D and rewriting the game's renderer registry keys
  changed nothing. The check precedes renderer selection.
- **Not the runtime or the prefix.** A fresh prefix, a different Proton, and pre-creating
  the compatdata directory each fixed *other* problems and not this one.
- **Not the wrong executable.** Several of these games ship a configuration launcher beside
  the game binary; picking the right one is necessary and not sufficient — both fail the
  same check.
- **Not the sandbox or a missing Flatpak permission.** The game is genuinely starting and
  then refusing.
- **Not a real shortage of anything.** Check the actual figures before believing the dialog.

### Fix

**1. Find out whether the game has a maintained engine.** This is the whole fix, and for a
game with any following it usually exists. Some that come up in a Ports folder:

| original | engine |
|---|---|
| FreeSpace / FreeSpace 2 | FreeSpace Open (`fs2open`) |
| Doom, Heretic, Hexen | GZDoom, Chocolate Doom |
| Quake / Quake II | vkQuake, yquake2, ioquake3 for Q3 |
| Morrowind | OpenMW |
| point-and-click adventures | ScummVM |
| DOS-era titles generally | dosbox-staging |

Prefer a **native Linux build**; it removes the whole compatibility layer rather than
working around it. Verify the download against the publisher's checksum — you are placing a
new binary on the machine.

**2. Point the port's launcher at the engine, with the working directory on the game data.**
Most engines take their data root from the current directory, so that `cd` is what puts the
engine on the original assets. Save data typically goes to an XDG path, so the game folder
is never written to.

```sh
game_dir='/home/<user>/retrodeck/roms/ports/<Game>/<data subdir>'
engine='/home/<user>/apps/<engine>/<engine binary>'

if [[ -f /.flatpak-info ]]; then
    exec flatpak-spawn --host bash -c 'cd "$1" && exec "$2"' _ "$game_dir" "$engine"
else
    cd "$game_dir"; exec "$engine"
fi
```

**3. Keep the old launcher as a dated `.bak` and delete nothing else.** The original
executables and any prefix cost nothing to leave in place.

Three traps specific to RetroDECK ports:

- **Detect the sandbox with `/.flatpak-info`, not `command -v flatpak-spawn`.** The
  `flatpak-spawn` binary is on the Bazzite **host** PATH too, so testing for it sends a
  host-side run down the sandbox branch, where it fails. `/.flatpak-info` exists only
  inside a sandbox.
- **A host-side engine needs `flatpak-spawn --host`** for host GL and, for an AppImage,
  host FUSE. That relies on the desktop-launch permission the other port wrappers use:
  `flatpak override --user --talk-name=org.freedesktop.Flatpak net.retrodeck.retrodeck`.
- **Nothing in the ES-DE gamelist changes.** The entry is still the `.sh`, and Ports still
  uses the `Script` emulator. Editing the gamelist for this would be overwritten by ES-DE
  on exit anyway.

### Verification

Launch it the way ES-DE does, from inside the sandbox, rather than from a host shell:

```sh
flatpak run --command=bash net.retrodeck.retrodeck -c '"/home/<user>/retrodeck/roms/ports/<Game>.sh"'
```

Then confirm by **seeing the game**, not by an exit code — see
[`../../../DRIVING-A-GAME-GUI.md`](../../../DRIVING-A-GAME-GUI.md) for reaching the display
from an SSH session, and note the `XAUTHORITY` trap there: a run without it exits 0 and
draws nothing, which looks like a different bug.

What was seen on the worked example:

- the game's own menu rendered from the original data, and on a second launch the profile
  the first run created — so it survives a restart and keeps state;
- **no refusal dialog** in the X window list, where there had been one every time;
- no output on stdout/stderr across a 100-second idle run;
- `SIGTERM` exits cleanly, leaving no `flatpak-spawn`, `bwrap` or engine processes — worth
  checking explicitly, because a port wrapper leaving a stuck tree makes RetroDECK look hung.

### When this entry does not fit

- **The dialog names a plausible figure**, or a limit the machine really does not meet.
  Then it is not this and the machine may genuinely be short of something.
- **The refusal window is absent from the window list** while the game still exits. Check
  `XAUTHORITY` first — a run without it exits 0 with an authorization message and no dialog
  at all, which is a different problem wearing the same clothes.
- **The engine also fails**, complaining about missing game data. That is a working
  directory or install-layout problem, not this one — see
  [zero-byte-asset-stub-fatal-error](../../backlog/emulation/zero-byte-asset-stub-fatal-error.md)
  if the data looks present but the engine dies on a specific file.
- **No engine exists for the game.** The diagnosis still holds and this fix does not. Most
  1990s titles never got a source port.

### Worked example — FreeSpace 2, 2026-08-28

Retail `FS2.exe` (1999) on a 48 GB host put up `Not Enough RAM` and blocked on it forever.
Three earlier attempts had gone at the graphics path: switching from the configuration
launcher `freespace2.exe` to `FS2.exe`, `PROTON_USE_WINED3D=1`, and rewriting the renderer
key in the prefix from `Direct 3D - DirectDraw HAL (640x480)` to
`Direct 3D - Primary Display Driver (32 bit) (1024x768)`. None could work, because the check
precedes renderer selection.

Fixed with FreeSpace Open 26.0.0, a native Linux AppImage, launched with the working
directory on the game's data folder. The retail executables and the Proton prefix were left
in place.

### Sightings

<!-- Newest first. `rdtroubleshoot kb sighting old-game-fails-its-own-startup-check "..."` appends here and moves
     last_confirmed forward. -->

- **2026-08-28** — FreeSpace 2 in the Ports system, as above. Filed originally as a
  title-specific entry and generalised once it was clear the diagnosis, the traps and the
  fix shape were all about the *class* of game rather than this one.

### Sources

- The RetroDECK log's `Launching game` block for the affected title
- `xwininfo -root -tree` with `DISPLAY` and the seated session's `XAUTHORITY`
- [`DRIVING-A-GAME-GUI.md`](../../../DRIVING-A-GAME-GUI.md)
