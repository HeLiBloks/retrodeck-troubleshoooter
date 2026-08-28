---
slug: ryujinx-black-screen-after-loading
area: input
status: fixed
first_seen: 2026-08-16
last_confirmed: 2026-08-28
verified: 2026-08-16
verified_by: the game drew its title screen after the pad was bound; rdtroubleshoot input reports "every connected pad has a matching profile"
signatures:
  - source: symptom
    pattern: black screen after (the game|it) loads
    note: audio usually works, which is what makes it read as a GPU fault
  - source: retrodeck-log
    pattern: Hid Remap: No matching controllers found
    note: repeats every two seconds for the whole session; logged at |W|, not |E|
  - source: retrodeck-log
    pattern: Application requests '(ProController|Handheld|JoyconPair)
    note: the same warning's second line, naming what the game wanted
  - source: checker
    pattern: Ryujinx input match
---

# Switch game loads to a black screen — no controller profile matches the connected pad

## TL;DR

The game is running and waiting for input it never receives — this is a **controller
binding**, not the GPU. Bind the pad that is actually plugged in: Ryujinx → Options →
Settings → Input → Player 1. Look for `Hid Remap: No matching controllers found` repeating
in the log to confirm. Note that the pad can be **plugged in and visible to the emulator**
and still not match, so "it's connected" does not rule this out.

---

## Engineer notes

### Symptom signature

The game starts, loads, and the screen stays black. Audio comes up. A handful of shaders
compile. Everything looks alive.

```
|W| Hid Remap: No matching controllers found.
    Application requests 'ProController, Handheld, JoyconPair'
    on 'Player1, Player2, Player3, Player4, Handheld'
```

Other tells:

- The warning repeats **every two seconds** until you quit — a repeating `|W|` is more
  informative here than any one-off `|E|`.
- `AudioRenderer AcquireSessionId: Registered new output (0)` — audio is up, so the process
  is healthy.
- Only ~4 shaders compiled, i.e. it never drew a real frame.
- **Severity misleads.** This is `|W|`, so an error-only grep misses it entirely.

### Cause

Ryujinx matches a pad to a profile by an id derived from the device, and will not fall back
on its own. If the only profile in `Config.json` is for a different pad, nothing binds:
`docked_mode: true` removes the Handheld fallback and `enable_keyboard: false` removes the
other, so there is no path left.

Measured 2026-08-16: a DualShock 4 *was* connected and Ryujinx *saw* it — `lsusb` showed
`054c:05c4`, and the emulator logged `Hid HandleJoyBatteryUpdated: PS4 Controller power
level: SDL_JOYSTICK_POWER_WIRED`. It simply had no profile whose id matched, because the
only binding was for an X360 pad.

### Diagnosis steps

1. `rdtroubleshoot input` — it derives the expected id for every connected pad and compares
   it against the profiles in `Config.json`.
2. If no pad is listed at all, none is connected: `joydev` must be loaded and a `js*` node
   must exist. That is a different (simpler) case — plug one in.
3. Confirm the repeating warning in the log, and note what the *application* requested.

### Fix

Easiest first:

1. **Bind the pad that is connected** — Options → Settings → Input → Player 1. The GUI is
   the reliable route.
2. **Add a keyboard binding** as a fallback for when no pad is present.
3. Turning **docked mode off** restores the Handheld option, but only once something is
   bound.

Editing `Config.json` directly is possible and the id is derivable rather than guessable:

```sh
rdtroubleshoot --guid <bustype> <vendor> <product> <version>   # hex, from /sys/class/input/inputN/id/
# DS4: rdtroubleshoot --guid 0003 054c 05c4 8111
#   -> 0-00000003-054c-0000-c405-000011810000
```

Button names in a profile are SDL-normalised (`A`, `B`, `LeftShoulder`, `DpadUp`), so a
mapping copies from one pad's profile to another unchanged.

**Close Ryujinx before editing `Config.json` — it rewrites the file on exit.** Same hazard
as ES-DE and gamelists.

### Verification

After binding, the game drew its title screen and accepted input, and the `Hid Remap`
warning stopped appearing. `rdtroubleshoot input` reports `every connected pad has a
matching profile`. Re-confirmed 2026-08-28: the DS4 profile is still bound as Player1 with
a keyboard as Player2.

### When this entry does not fit

- No `Hid Remap` line in the log at all — look for a real `|E|`, and check the GPU lines.
  On this hardware the discrete card is correctly selected and has never been the cause.
- The game never reaches "loaded" — that is a launch failure, not an input one. If the file
  is an `…800` NSP it is a title update and contains no application; see
  [switch-update-nsp-never-launches](../emulation/switch-update-nsp-never-launches.md).
- Audio never starts either — the process is not healthy, so this is something else.

### Sightings

- **2026-08-28** — re-confirmed still fixed; profile intact, no pad connected at the time,
  and the checker correctly declines to compare bindings against nothing.
- **2026-08-16** — DualShock 4 connected and visible, only an X360 profile present. 2m37s
  session, warning every 2s, 4 shaders, audio up. Fixed by binding the pad.

### Sources

- Log excerpt: `~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log`
- Checker output: `rdtroubleshoot input`
- Eval fixture: `../../evals/ryujinx-black-screen-after-loading.md`
- Background: [docs/EMULATION.md](../../../EMULATION.md) § "A black screen after loading is an unbound pad"
