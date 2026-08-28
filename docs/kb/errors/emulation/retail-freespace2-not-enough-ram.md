---
slug: retail-freespace2-not-enough-ram
area: emulation
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: the FS2 main hall and then the Choose Pilot screen rendered from the retail .vp data, screenshotted from a launch made through the RetroDECK sandbox, with no Not Enough RAM window on the X server and a clean exit leaving no flatpak-spawn/bwrap/engine processes
signatures:
  - source: symptom
    pattern: (freespace).*(0\s*mb|not enough ram|won'?t (start|launch)|exits? (immediately|on ok))
    note: a dialog claiming 0MB of free memory, and the game exits when it is dismissed
  - source: retrodeck-log
    pattern: Proton: Upgrading prefix from None to [\d.\-]+ \([^)]*freespace2-proton
    note: ES-DE captured this as the launched game's entire output; "from None" on every launch means the prefix never completed a run, and after the fix the line cannot appear at all because the port no longer uses Proton
---

# FreeSpace 2 shows "0MB of free memory" and exits

## TL;DR

**Stop launching the retail `FS2.exe` and run the FreeSpace Open engine against the retail
data instead.** The 1999 executable misreports memory on a machine this size and refuses to
start; no Proton version, renderer key or `PROTON_USE_WINED3D` setting reaches that check,
because it runs before any renderer is chosen. Download an
[FSO release](https://github.com/scp-fs2open/fs2open.github.com/releases), point the port's
`.sh` at it, and `cd` into the directory holding the `.vp` files first — FSO takes its game
root from the working directory, so it reads the retail data in place and nothing in the
game folder has to change.

---

## Engineer notes

### Symptom signature

What the user sees:

```
FreeSpace has detected that you only have 0MB of free memory.
FreeSpace requires at least 32MB of memory to run.
```

The window really is on the X server, and its title is the most distinctive thing about it:

```
0x2600001 "Not Enough RAM": ("steam_proton" "steam_proton")  280x154+820+453
```

In the RetroDECK log the whole failure looks like a *successful* launch — there is no error
line at all, only the launch, two lines of Proton noise, and a play time that is really the
user reading the dialog:

```
[INFO] [ES-DE] Launching game "FreeSpace 2" from system "Ports (ports)"...
[DEBUG] [ES-DE] FileData::launchGame(): Using default emulator "Script"
[INFO] [ES-DE] /usr/bin/bash /home/<user>/retrodeck/roms/ports/FreeSpace\ 2.sh
[DEBUG] [ES-DE] Output from launched game:
Proton: Upgrading prefix from None to 11.0-100 (/var/home/<user>/retrodeck/saves/freespace2-proton/)
ntsync: up and running.
[DEBUG] [ES-DE] FileData::setPlayMetadata(): Play time was 83 seconds
```

Other tells:

- The wrapper exits **0** and no Wine or Proton process is left behind, so nothing looks
  crashed.
- `Upgrading prefix from None` appears on **every** launch. The prefix never finishes a run,
  so it is rebuilt each time — a quiet sign that the game is not reaching steady state.
- ES-DE still records play time and updates the gamelist, so the entry looks played.

### What is known

Measured on the test machine, 2026-08-28 (12 cores, 48 GB RAM, Bazzite 44):

- **The dialog is real and it blocks.** Running `FS2.exe` under Proton from a shell that has
  a working `XAUTHORITY` for the desktop session leaves the `Not Enough RAM` window listed by
  `xwininfo -root -tree`, and the process sits on it indefinitely.
- **It never reaches graphics initialisation.** The check fires first, which is why every
  renderer-side change was inert.
- **`FS2/freespace2.exe` is the original configuration launcher, not the game.** The retail
  game executable is `FS2/FS2.exe`. Switching to it was correct and changed nothing, because
  both hit the same check.
- Running it over SSH without `XAUTHORITY` is misleading: it prints
  `Authorization required, but no authorization protocol specified` and exits 0 with no
  dialog, which looks like a different failure. **Set `XAUTHORITY` to the session's
  `/run/user/<uid>/xauth_*` file before concluding anything.**

### What has been ruled out

- **Not the Proton prefix.** Creating `saves/freespace2-proton` before launch fixed an
  earlier, genuinely different failure (Proton could not create `pfx.lock`) and does not
  touch this one.
- **Not the renderer.** `PROTON_USE_WINED3D=1`, and rewriting
  `Software\Wow6432Node\Volition\FreeSpace2` in the prefix from
  `Direct 3D - DirectDraw HAL (640x480)` to `Direct 3D - Primary Display Driver (32 bit)
  (1024x768)`, both leave the dialog exactly as it was.
- **Not the wrong executable.** `FS2.exe` is the game; `freespace2.exe` is the config tool.
  Both fail the same way.
- **Not the RetroDECK sandbox and not a missing Flatpak permission.** The
  `--talk-name=org.freedesktop.Flatpak` override is in place and `flatpak-spawn --host`
  reaches Proton correctly — the game is genuinely starting, and then refusing.
- **Not a real shortage of memory.** `free -m` reports 47527 MB total and 40407 MB
  available at the moment the dialog appears.

### Fix

Replace the executable, not the wrapper's environment. **FreeSpace Open** is the community
engine for this game; it reads the retail data directly, so the retail install stays exactly
where it is.

**Correction, from a later session.** This entry first said FSO "reads the retail `.vp`
files". That is the general case but was not true of the install it was written against:
seven of its eight packs turned out to be index-only stubs and the game was really running
off the loose extracted `data/` tree. The `cd` below is what matters either way — it puts
FSO's game root on whichever of the two the install actually has. See
[fso-fatal-error-zero-byte-anim](../../backlog/emulation/fso-fatal-error-zero-byte-anim.md)
for how to tell a real pack from a stripped one.

1. **Get a native Linux FSO build.** The releases are at
   `https://github.com/scp-fs2open/fs2open.github.com/releases`. The Linux x86_64 tarball
   contains AppImages. Verify the download against the release's published SHA256 — this is
   a game engine being placed on the box, so check it rather than trusting the transfer.

   ```sh
   mkdir -p ~/apps/fs2open && cd ~/apps/fs2open
   curl -fL --retry 3 -o fso.tar.gz \
     https://github.com/scp-fs2open/fs2open.github.com/releases/download/release_26_0_0/fs2_open_26_0_0-builds-Linux-x86_64.tar.gz
   sha256sum fso.tar.gz     # must equal the SHA256 on the release page
   tar xzf fso.tar.gz
   ```

2. **Point the port's launcher at it, with the working directory on the game data.** FSO
   derives its game root from the working directory; that single `cd` is what puts it on
   `root_fs2.vp` and the rest. Pilots and config go to
   `~/.local/share/HardLightProductions/FreeSpaceOpen/`, so the game folder is never
   written to.

   ```sh
   game_dir='/home/<user>/retrodeck/roms/ports/FreeSpace 2/FS2'
   engine='/home/<user>/apps/fs2open/fs2_open_26_0_0_x64_SSE2.AppImage'

   if [[ -f /.flatpak-info ]]; then
       exec flatpak-spawn --host bash -c 'cd "$1" && exec "$2"' _ "$game_dir" "$engine"
   else
       cd "$game_dir"; exec "$engine"
   fi
   ```

3. **Keep the old launcher as a dated `.bak`, and delete nothing else.** The retail
   executables and the Proton prefix cost nothing to leave in place, and the prefix is the
   only record of the earlier configuration.

Three things that are easy to get wrong here:

- **Detect the sandbox with `/.flatpak-info`, not `command -v flatpak-spawn`.**
  `flatpak-spawn` is on the Bazzite **host** PATH as well, so testing for the binary sends a
  host-side run down the sandbox branch, where it fails. `/.flatpak-info` exists only inside
  a sandbox.
- **The AppImage must run on the host**, via `flatpak-spawn --host`, because it needs host
  FUSE and the host GL stack. That in turn needs the Ports desktop-launch permission that
  the other port wrappers already rely on:
  `flatpak override --user --talk-name=org.freedesktop.Flatpak net.retrodeck.retrodeck`.
- **Nothing in the ES-DE gamelist changes.** The entry is still `./FreeSpace 2.sh` and Ports
  still uses the `Script` emulator. Editing the gamelist for this would be wrong, and would
  be overwritten by ES-DE on exit anyway.

### Verification

What was **seen** on the machine, 2026-08-28, launching the way ES-DE launches it:

```sh
flatpak run --command=bash net.retrodeck.retrodeck \
  -c '"/home/<user>/retrodeck/roms/ports/FreeSpace 2.sh"'
```

- The **FS2 main hall** drawn from the retail data, captured off the live X server, with
  `FreeSpace 2 Open v26.0.0 OpenGL` on screen. Rendering FS2's own interface art and font is
  what proves the `.vp` files were found.
- On a second launch, the **Choose Pilot** screen listing the pilot the first run created —
  so the fix survives a restart and keeps state.
- **No `Not Enough RAM` window** on the X server at any point, where the retail executable
  put one there every time.
- **No output at all** on stdout/stderr across a 100-second idle run at the main hall.
- **`SIGTERM` exits cleanly**, leaving no `flatpak-spawn`, `bwrap` or engine processes. Worth
  checking explicitly: a port wrapper on this box has previously left a stuck tree that made
  RetroDECK look hung.

Not verified: gameplay past the main hall. FSO takes relative mouse input, so it cannot be
driven from an SSH session — that last step needs a human at the keyboard.

### When this entry does not fit

- **The dialog names a non-zero amount of memory**, or a different limit. Then it is not this
  overflow and the machine may genuinely be short of something.
- **`Not Enough RAM` is absent from the window list** while the game still exits. Then the
  failure is somewhere else — check `XAUTHORITY` first, because a run without it exits 0 with
  `Authorization required, but no authorization protocol specified` and no dialog at all,
  which is a different problem wearing the same clothes.
- **FSO also fails**, with a message about missing game data. Then the working directory is
  wrong, or the `.vp` files are not where the launcher thinks — that is a path problem, not
  this one.
- The game is a **different** old title. The pattern generalises — a 1990s Windows game that
  refuses to start over its own memory check on a large-RAM host — but the fix does not.
  FreeSpace Open exists because this game got a community engine; most do not.

### Sightings

<!-- Newest first. `rdtroubleshoot kb sighting retail-freespace2-not-enough-ram "..."` appends here and moves
     last_confirmed forward. A second sighting is the cue to investigate and promote. -->

- **2026-08-28, retraction.** This entry originally recorded
  `Error: animation (cb_train-01_a.ani) has invalid fps of zero` as a one-off that "did not
  recur". **That was wrong**, and the user hit it in normal play the same evening. It now
  has its own entry:
  [fso-fatal-error-zero-byte-anim](../../backlog/emulation/fso-fatal-error-zero-byte-anim.md).
  The reasoning that produced the bad call is worth keeping: the error was declared
  non-reproducing on the strength of a 100-second idle run, a relaunch and a `SIGTERM` — none
  of which load an animation, because the main hall never does. **Absence of a symptom under
  conditions that cannot trigger it is not evidence.** Identify the trigger before calling
  something a one-off.
- **2026-08-28** — resolved with FSO 26.0.0 (see *Fix* and *Verification*).
- **2026-08-28** — first seen. Ports entry `FreeSpace 2.sh` launched from ES-DE on the
  Bazzite box; handed over as an open case in `roms/ports/HANDOFF.md` after the executable,
  prefix and renderer changes had all been tried.

### Sources

- Log excerpt: `~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log`,
  the `Launching game "FreeSpace 2"` block
- Window list: `xwininfo -root -tree` with `DISPLAY=:0` and the session's `XAUTHORITY`
- Handoff: `~/retrodeck/roms/ports/HANDOFF.md`
