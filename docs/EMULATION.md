# Emulation troubleshooting

Findings from actually reading the logs on the test machine, so nobody re-derives them. This
is about RetroDECK and its emulators; scraping is in [SCRAPING.md](SCRAPING.md) and the
host in [BAZZITE-OS.md](BAZZITE-OS.md).

## Where the logs are

```
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log.{1,2,3}.tar.gz
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck_bios_check.log
```

`retrodeck.log` interleaves ES-DE's own lines with the **emulator's stdout**, so a Ryujinx
or RetroArch session appears inline, timestamped from its own start (`00:00:12.345`) rather
than wall clock. Rotated logs are gzipped **tarballs** — read them with `tar -xzOf <file>`,
not `zcat`.

First pass by hand:

```sh
L=~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
grep -nE 'Launching game .* from system' "$L" | tail        # what was started, and when
grep -aE '\|E\|' "$L" | grep -av mesa_glthread | tail -20   # real errors only
```

`ATTENTION: default value of option mesa_glthread overridden by environment` is logged at
`|E|` severity by Ryujinx and is **noise** — a Mesa message, on a machine where Mesa is not
driving the game. Filter it or it drowns everything. `rdtroubleshoot emulation` does, and
counts what it filtered.

## Checking whether RetroDECK is running

```sh
pgrep -a -f '[e]s-de|[e]mulationstation|[n]et.retrodeck'
```

The bracket trick matters. A plain `pgrep -af 'es-de|...'` **matches your own shell's
command line**, because the pattern is in it, and reports RetroDECK running when it is not.
This bit us over SSH.

Why it matters at all: **ES-DE rewrites every gamelist on exit**, so any tool that writes
a gamelist while RetroDECK is open loses the lot — and reports success on the way out.

## A black screen after loading is an unbound pad, not the GPU

This is the single most misleading symptom in the whole stack, so it gets the most space.

Symptom: the game starts, loads, and the screen stays black. Audio comes up. A handful of
shaders compile. Everything looks alive.

What the log shows, every two seconds until you quit:

```
|W| Hid Remap: No matching controllers found.
    Application requests 'ProController, Handheld, JoyconPair'
    on 'Player1, Player2, Player3, Player4, Handheld'
```

The game is running and waiting for input that never arrives. Only **4 shaders** loaded,
i.e. it never drew a real frame.

**Measured on this machine 2026-08-16, and the profile was the whole story.** A DualShock 4
*was* connected — `lsusb` showed `054c:05c4 Sony Corp. DualShock 4 [CUH-ZCT1x]` on
`/dev/input/js0`, and Ryujinx itself logged `Hid HandleJoyBatteryUpdated: PS4 Controller
power level: SDL_JOYSTICK_POWER_WIRED`. It saw the pad. It simply had no profile whose id
matched it, because the only binding in `Config.json` was for an X360 pad, `docked_mode:
true` removed the Handheld fallback and `enable_keyboard: false` removed the other.

### The controller id is derivable, not guessable

Ryujinx stores the id as a .NET `Guid` laid over SDL's 16-byte joystick GUID, so it comes
from the kernel rather than from trial and error. Read the four ids out of the device's
sysfs `id/` directory and:

```sh
rdtroubleshoot --guid <bustype> <vendor> <product> <version>
# DS4: rdtroubleshoot --guid 0003 054c 05c4 8111
#   -> 0-00000003-054c-0000-c405-000011810000
```

The layout, for when the tool is not to hand: SDL writes four little-endian 16-bit values
each followed by two zero bytes — `03 00 00 00 | 4c 05 00 00 | c4 05 00 00 | 11 81 00 00`.
.NET's `Guid(byte[])` then reads the first three fields little-endian and the last eight
bytes raw, which is why the vendor appears byte-swapped in the second group and the product
does not in the fourth. `rdtroubleshoot input` derives this for every connected pad and
compares it against the profiles actually in `Config.json`.

Fixes, easiest first:

1. **Bind the pad that is actually connected** — Options → Settings → Input → Player 1. The
   GUI is the reliable route; the derivation above is only needed when editing the file.
2. **Add a keyboard binding** as a fallback for when no pad is present.
3. Turning **docked mode off** restores the Handheld option, but only once something is bound.

Button names in a profile are SDL-normalised (`A`, `B`, `LeftShoulder`, `DpadUp`), so a
mapping copies across from one pad's profile to another unchanged.

**Close Ryujinx before editing `Config.json` — it rewrites the file on exit.** Same hazard
as ES-DE and gamelists.

## Switch (Ryujinx)

RetroDECK 0.10.9b launches Switch titles through `~/retrodeck/ryubing-launcher` into
**Ryujinx (Ryubing) 1.3.3**, flatpak `io.github.ryubing.Ryujinx`:

```
~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/Config.json
~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/system/prod.keys
~/.var/app/io.github.ryubing.Ryujinx/config/Ryujinx/games/<titleid>/
```

Firmware 22.5.0 and `prod.keys` are installed and working — if a game fails, that is not
the cause. `games/` holds one directory per **base** title the emulator has seen.

### An update NSP is not a game, and never launches

Verified 2026-08-14: launching `Super Woden GP II [<titleid>800][v131072].nsp` gives

```
|E| Application CheckLaunchState: Couldn't find any application in '...[<titleid>800][v131072].nsp'.
```

That is correct behaviour. The title-ID suffix tells you which file is which:

| suffix | what it is |
|---|---|
| `...000` + `[v0]` | the base game — this is the one you launch |
| `...800` + `[v65536]`, `[v131072]`, … | a **title update**, containing no application |

**Do not delete the update NSPs.** Ryujinx references them by path once registered. To
apply one: right-click the base game in Ryujinx → **Manage Title Updates** → add the
`...800` file → pick the version. Mark them `<hidden>true</hidden>` in `gamelist.xml` and
keep `ShowHiddenGames=false` so ES-DE stops offering them.

### Ryujinx's sandbox is read-only on home

Measured: `filesystems=home:ro`. It can load a ROM from `~/retrodeck` and **cannot write a
save beside it**; its own `~/.var/app` tree is always writable, which is why most things
work and only some fail. `rdtroubleshoot flatpak` reports this as a WARN with the override
command.

### The GPU is not the problem

Recorded so nobody re-investigates it on this hardware:

```
PrintGpuInformation: NVIDIA GeForce GTX 1650 Ti (Vulkan v1.4.312, Driver v580.173.2.0)
GPU Memory: 4342 MiB
```

`Config.json` has `graphics_backend: Vulkan` and `preferred_gpu: 0x10DE_0x1F95` — vendor
`0x10DE` is NVIDIA and `0x1F95` is the GTX 1650 Ti Mobile, so Ryujinx is correctly pinned
to the discrete card and **not** falling back to the Ryzen 4600H's Renoir iGPU, which is
the usual hybrid-graphics trap on a laptop. No Vulkan or shader errors appear in any run.

## Sega Model 3 (Supermodel)

RetroDECK bundles **no** Model 3 emulator. The custom `model3` system launches the user
Flatpak `com.supermodel3.Supermodel` through
`~/retrodeck/ES-DE/custom_systems/supermodel-launch.sh`.

Supermodel 0.3a fails with `OpenGL initialization failed: Unknown error` when
`WAYLAND_DISPLAY` is set. The launcher therefore does **two** things, both load-bearing:

1. changes directory to `~/.var/app/com.supermodel3.Supermodel/config/supermodel`, so
   `Assets/` resolves;
2. invokes the host Flatpak with `WAYLAND_DISPLAY=`, forcing the working X11/OpenGL path.

**Do not remove either half.** Smoke-tested through the launcher with `daytona2`, `getbass`
and `harleya`: all reported GPU information and a valid ROM-set title and stayed running.
`vf3a` also started; its missing `driveboard_program` ROM is optional and not a launch
blocker.

## Two gamelist traps that look like corruption

### A gamelist can have two root elements

With a per-system emulator override set, ES-DE writes
`<alternativeEmulator><label>...</label></alternativeEmulator>` as a **sibling** of
`<gameList>`. ES-DE's own parser accepts it. Two roots is not well-formed XML, so
`ElementTree` refuses the file with `junk after document element`, and anything built on it
reports the folder as broken on every run for as long as the override is set.

`rdtroubleshoot` handles it and reports the affected systems as INFO. If you write your own
tool: locate the `<gameList>...</gameList>` span and parse that, but **re-raise the original
error when no `<gameList>` is found** — turning a corrupt gamelist into a quietly truncated
one is the worst outcome available.

### `/home` vs `/var/home` is not cosmetic

`$HOME` on Bazzite is `/home/retro`, a symlink to `/var/home/retro`. Both spellings
reach the same directory. ES-DE and Skyscraper match old gamelist entries to new ones by the
**raw `<path>` string**, so a file holding both spellings loses every entry under the
minority one: generating `model2` with the resolved spelling once lost 7 of 59 descriptions
and 22 playcount/lastplayed tags.

Never "fix" a ROM path with `realpath`. That is precisely what triggers it.

## ES-DE finds media by filename, not by gamelist tag

`gamelist.xml` has no `<image>`/`<video>` tags; ES-DE looks under
`downloaded_media/<system>/<mediatype>/` for a file whose stem matches the ROM's. Two
consequences worth knowing when art is wrong:

- An external scraper is drop-in safe, and a stale `<image>` tag in a gamelist is inert.
- Where two files share a stem, **ES-DE probes `.jpg` before `.png`**. A `.jpg` cover plate
  sitting beside a real `.png` screenshot is what shows.
