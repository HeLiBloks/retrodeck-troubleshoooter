---
name: read-retrodeck-logs
description: Read RetroDECK, ES-DE and emulator logs correctly - where they are, how to open the rotated ones, which error lines are noise, and which repeating warning explains a black screen. Use whenever a log needs interpreting rather than a check needs running.
---

# Reading the logs

```
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log.{1,2,3}.tar.gz
~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck_bios_check.log
~/.var/app/net.retrodeck.retrodeck/config/retroarch/playlists/builtin/content_history.lpl
```

Four things about this file before you grep it:

1. It **interleaves ES-DE's own lines with the emulator's stdout**, so a Ryujinx or
   RetroArch session appears inline, timestamped from **its own start** (`00:00:12.345`)
   rather than wall clock.
2. Rotated logs are gzipped **tarballs**. Use `tar -xzOf <file>`, not `zcat`.
3. `mesa_glthread` / `ATTENTION: default value of option ...` is logged at **`|E|`
   severity** by Ryujinx and is **noise** — a Mesa message, on a machine where Mesa is not
   driving the game. Unfiltered it drowns everything real.
4. It is not reliably UTF-8. Decode with `errors="replace"`, or `grep -a`.

## 0. Before anything: check what is already known

```sh
rdtroubleshoot kb search "<the user's words>"
rdtroubleshoot --kb            # annotates each WARN/FAIL with the entries covering it
```

A hit in `errors/` means the answer is already written — reply from its TL;DR. A hit in
`backlog/` means it is known and unresolved, which is still a real answer. Full procedure in
the `kb-lookup` skill; recording what you find is in `document-finding`.

## The first pass

```sh
L=~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log

grep -naE "Launching game .* from system" "$L" | tail       # what was started, and when
grep -aE '\|E\|' "$L" | grep -av mesa_glthread | tail -20   # real errors only
grep -aE '\|W\|' "$L" | sort | uniq -c | sort -rn | head    # repeating warnings
```

Or let the checker do it, which filters the noise and counts what it filtered:

```sh
./rdtroubleshoot emulation
```

## Lines worth recognising

| line | meaning |
|---|---|
| `\|W\| Hid Remap: No matching controllers found` **repeating every 2 s** | the game is running and waiting for input. **This is the black-screen cause.** Not a GPU fault |
| `\|E\| Application CheckLaunchState: Couldn't find any application in '...800...nsp'` | correct behaviour — that file is a **title update**, not a game |
| `AudioRenderer AcquireSessionId: Registered new output` | the game really is running |
| only ~4 shaders compiled | it never drew a real frame |
| `PrintGpuInformation: NVIDIA GeForce GTX 1650 Ti` | the discrete card is in use; hybrid-graphics fallback is **not** the problem here |
| `OpenGL initialization failed: Unknown error` (Supermodel) | `WAYLAND_DISPLAY` is set; the launcher must clear it |
| `\|E\| ... mesa_glthread ...` | **noise**, filter it |

A repeating `|W|` is often more informative than a one-off `|E|`. The black-screen case is
exactly that shape: warning severity, repeating, with no error at all.

## The other logs

- **`retrodeck_bios_check.log`** — grep for `missing`. A missing BIOS stops the core loading
  and presents as a broken ROM.
- **`content_history.lpl`** — RetroArch's own recently-played list; useful for confirming
  whether a core ever actually started.
- **The journal**, for anything that never reached RetroDECK's own log:
  ```sh
  journalctl --user -b -t net.retrodeck.retrodeck | tail -40
  journalctl -b -g 'avc:.*denied' | tail -20        # see the diagnose-host skill first
  ```

## Reporting

Quote the line, not your paraphrase of it, and say which file and roughly when. State
explicitly when a candidate cause has been **ruled out** — "the GPU is initialising
correctly, so this is not a driver problem" is worth as much as the finding, and stops the
next session re-deriving it.
