---
slug: ryujinx-saves-lost-sandbox-home-readonly
area: flatpak
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: rdtroubleshoot flatpak --probe-sandbox confirms the tree is readable but the grant is home:ro; an override adds rw
signatures:
  - source: symptom
    pattern: save (file )?(vanish|disappear|not saved|lost)
    note: reads as data loss; the ROM still loads fine, which is the confusing part
  - source: checker
    pattern: Ryujinx sandbox
    note: the check reports the grant and whether it is writable
---

# An emulator loads a ROM but cannot write beside it — the sandbox grant is read-only

## TL;DR

The emulator's Flatpak sandbox can **read** the ROM folder and not **write** to it, so
anything it tries to save next to the game fails. Grant write access to just that path:

```sh
flatpak override --user --filesystem=~/retrodeck io.github.ryubing.Ryujinx
```

Check first with `rdtroubleshoot flatpak`, which names the grant. Do **not** widen the
sandbox to `host` to make it go away — grant the specific path.

---

## Engineer notes

### Symptom signature

Nothing in a log says "permission denied to the ROM folder"; the game simply behaves as
though the save did not happen. The evidence is the grant itself:

```
$ flatpak info --show-permissions io.github.ryubing.Ryujinx
[Context]
filesystems=home:ro;xdg-pictures;...
```

Other tells:

- The ROM **loads normally**, which is what makes this hard to see: read access is
  sufficient for everything except the save.
- The emulator's own data directory (`~/.var/app/<id>/`) is always writable, so most state
  persists and only the parts written outside it are lost.
- `rdtroubleshoot flatpak` reports `reachable read-only via 'home:ro'; writes beside the
  ROM will fail`.

### Cause

`filesystems=home:ro` grants the whole of `$HOME` read-only. Measured on this machine
2026-08-28: RetroDECK holds `filesystems=host` and is unconstrained, Supermodel holds
`home;host:ro`, and **Ryujinx holds `home:ro`** — so it is the one app of the three that
cannot write into the ROM tree.

Worth knowing about the shape of the grant: the ROM tree here is a **separate filesystem**
mounted under `$HOME`. A `home` grant does carry a submount along — confirmed by
`--probe-sandbox`, which runs `sh` inside the app's own runtime and reads the directory —
so the mount is not the problem. Only the `:ro` is.

### Diagnosis steps

1. `rdtroubleshoot flatpak` — reports each app's grant and whether it covers the ROM tree
   writably.
2. `rdtroubleshoot flatpak --probe-sandbox` — asks the sandbox itself, which distinguishes
   "the grant does not cover this" from "the grant is read-only". Starts no emulator and
   writes nothing.
3. `flatpak override --user --show <app-id>` — an override can be the reason for a grant
   you cannot explain from the app's manifest.

### Fix

```sh
flatpak override --user --filesystem=~/retrodeck io.github.ryubing.Ryujinx
flatpak override --user --show io.github.ryubing.Ryujinx      # confirm
flatpak override --user --reset io.github.ryubing.Ryujinx     # undo, if needed
```

Grant the narrowest path that works. `--filesystem=host` would also fix it and is the wrong
answer: it removes the sandbox's value for one directory's sake.

### Verification

`rdtroubleshoot flatpak` moves from `WARN … reachable read-only via 'home:ro'` to a `PASS`
naming the new grant, and `--probe-sandbox` still reads the tree from inside the sandbox.
The definitive check is behavioural: make a save in-game, quit, and confirm it is still
there.

### When this entry does not fit

- The app's grant already includes the path writably — then the failure is elsewhere; check
  the ROM volume is not mounted read-only (`rdtroubleshoot emulation` reports that) and the
  SELinux label on the tree.
- The system shows **no games at all** rather than failing to save — that is a grant that
  does not cover the path, not a `:ro` one. Same fix shape, different diagnosis.
- The emulator is RetroDECK itself — it holds `filesystems=host` here, so this cannot be it.

### Sightings

- **2026-08-28** — found by `rdtroubleshoot flatpak` on the test machine rather than by a
  user report: Ryujinx's grant is `home:ro` while RetroDECK's is `host`. A latent case, so
  no save had been lost yet.

### Sources

- Checker output: `rdtroubleshoot flatpak --probe-sandbox`
- Eval fixture: `../../evals/ryujinx-saves-lost-sandbox-home-readonly.md`
- Background: [docs/BAZZITE-OS.md](../../../BAZZITE-OS.md) § "Flatpak: the sandbox is the usual culprit"
