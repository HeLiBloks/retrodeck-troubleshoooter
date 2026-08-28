---
slug: ryujinx-saves-lost-sandbox-home-readonly
kb_entry: ../errors/flatpak/ryujinx-saves-lost-sandbox-home-readonly.md
recorded: 2026-08-28
verified_by: rdtroubleshoot flatpak --probe-sandbox
sources:
  - kind: checker
    command: rdtroubleshoot flatpak --probe-sandbox
---

# Eval fixture — ryujinx-saves-lost-sandbox-home-readonly

## Input — verbatim evidence

```
WARN  Ryujinx sandbox       /home/<user>/retrodeck/roms is reachable read-only via 'home:ro'; writes beside the ROM will fail
                            -> flatpak override --user --filesystem=/home/<user>/retrodeck/roms io.github.ryubing.Ryujinx   # adds rw
PASS  Ryujinx sandbox probe read /home/<user>/retrodeck/roms inside the sandbox: 3do, adam, amiga
PASS  RetroDECK sandbox     /home/<user>/retrodeck/roms reachable (whole host)
```

## Expected — diagnosis anchor

- **Match:** `ryujinx-saves-lost-sandbox-home-readonly` via signature `checker: Ryujinx sandbox`
- **Diagnosis:** the grant is `home:ro`, so the tree is readable and not writable; a save
  written beside the ROM fails while the ROM itself loads normally.
- **Lead action:** `flatpak override --user --filesystem=~/retrodeck io.github.ryubing.Ryujinx`

## Notes

The two `PASS` lines are the point of keeping this fixture. The probe **succeeds** — the
sandbox really can read the tree, including across the separate filesystem mounted under
`$HOME` — so a diagnosis that treats "probe passed" as "sandbox is fine" gets this wrong.
Read access and write access are separate answers, and only the static grant distinguishes
them. RetroDECK passing on the same path is the contrast that shows the fault is per-app.
