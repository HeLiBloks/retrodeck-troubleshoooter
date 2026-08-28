---
name: diagnose-emulation
description: Diagnose a RetroDECK game that will not launch, shows a black screen, has no art, or has the wrong metadata. Use when a specific system or title misbehaves, when a controller is not recognised, or when asked why an emulator fails on the Bazzite box.
---

# Diagnosing an emulation problem

Run the checker first, then read the log. Do not start by editing configuration — three of
the four most common causes here look like something else entirely, and two of them are
normal states rather than faults.

## 1. Always start here

```sh
./rdtroubleshoot emulation input
```

Read-only, safe while RetroDECK is open. Exit 0 healthy / 1 warnings / 2 failures.
Add `-q` for only the WARN and FAIL lines, `--json` to consume it.

## 2. Match the symptom

| symptom | first suspicion | check |
|---|---|---|
| loads, then **black screen**, audio works | **unbound controller**, not the GPU | `./rdtroubleshoot input` |
| a system shows **no games** | ROM format not in the platform's list, or a sandbox that cannot see the tree | `./rdtroubleshoot flatpak` |
| one `.nsp` never launches | it is a **title update** (`...800`), which contains no application | `./rdtroubleshoot emulation` |
| a **save vanishes** | the emulator's sandbox has `home:ro` | `./rdtroubleshoot flatpak` |
| art is **wrong or missing** | ES-DE matches media by filename; a `.jpg` beside a `.png` wins | `docs/EMULATION.md` |
| **metadata** wrong or thin | see the `diagnose-scraping` skill | — |
| Model 3 dies on **OpenGL init** | the launcher's `WAYLAND_DISPLAY=` workaround | `./rdtroubleshoot emulation` |
| "it worked yesterday" | a **staged ostree deployment** not yet booted | `./rdtroubleshoot os` |

## 3. The black-screen case, in detail

This is the one worth knowing by heart, because the log says `|W|` not `|E|` and the game
is genuinely running.

`Hid Remap: No matching controllers found`, repeating every two seconds, means the game is
waiting for input that never arrives. The pad may well be **connected and visible** to the
emulator — it simply has no profile whose id matches.

`./rdtroubleshoot input` derives the id Ryujinx expects for every connected pad and compares
it against `Config.json`. To derive one by hand from sysfs:

```sh
./rdtroubleshoot --guid <bustype> <vendor> <product> <version>   # all hex, from /sys/class/input/inputN/id/
```

Fix in the GUI (Options → Settings → Input → Player 1) rather than the file where you can.
**Close Ryujinx before editing `Config.json` — it rewrites the file on exit.**

## 4. Then read the log

`./rdtroubleshoot emulation` scans the tail and filters the noise. To read it yourself, use
the procedure in the `read-retrodeck-logs` skill — in particular, `mesa_glthread` is logged
at `|E|` severity and is noise, and rotated logs are gzipped **tarballs**, not gzip streams.

## 5. Rules when you change something

- **RetroDECK must be closed before anything writes a gamelist.** ES-DE rewrites every
  gamelist on exit, so a write against an open RetroDECK reports success and is lost.
- **Never `realpath` a ROM path.** `/home/retro` and `/var/home/retro` are the same
  directory and not interchangeable in a gamelist; mixing them drops entries on the next
  generate.
- **Never delete an update NSP.** Ryujinx references it by path. Mark it `<hidden>` instead.
- **Do not remove either half of the Supermodel workaround** (the `cd`, and
  `WAYLAND_DISPLAY=`).
- Back up any config you edit, and say in your report what you changed and where the backup
  is.

Full background, with the measurements behind each of these: [docs/EMULATION.md](../../../docs/EMULATION.md).
