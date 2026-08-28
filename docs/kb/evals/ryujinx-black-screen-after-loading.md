---
slug: ryujinx-black-screen-after-loading
kb_entry: ../errors/input/ryujinx-black-screen-after-loading.md
recorded: 2026-08-16
verified_by: the game drew its title screen after the pad was bound
sources:
  - kind: log
    path: ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log
  - kind: checker
    command: rdtroubleshoot input
---

# Eval fixture — ryujinx-black-screen-after-loading

## Input — verbatim evidence

The question as asked:

> the switch game just shows a black screen after it loads, audio works though. gpu problem?

The log lines behind it:

```
|I| Application AudioRenderer AcquireSessionId: Registered new output (0)
|W| Hid Remap: No matching controllers found.
    Application requests 'ProController, Handheld, JoyconPair'
    on 'Player1, Player2, Player3, Player4, Handheld'
|W| Hid Remap: No matching controllers found.
|I| Gpu PrintGpuInformation: NVIDIA GeForce GTX 1650 Ti (Vulkan v1.4.312, Driver v580.173.2.0)
```

## Expected — diagnosis anchor

- **Match:** `ryujinx-black-screen-after-loading` via signature
  `retrodeck-log: Hid Remap: No matching controllers found`
- **Diagnosis:** the pad connected has no matching profile in `Config.json`, so nothing
  binds and the game waits for input for ever. Not the GPU.
- **Lead action:** bind the connected pad under Options → Settings → Input → Player 1.

## Notes

This fixture exists mostly for the **red herring**. The user proposes the GPU, audio
working makes the process look healthy, and the GPU line in the log is present and
perfectly fine — so a diagnosis that reads the GPU line and stops is wrong in a way that
sounds authoritative. The distinguishing evidence is a `|W|`, which an error-severity grep
never sees.

A second near-miss to see past: if the connected-pad list is empty, the answer is "plug one
in", not "fix the binding". The checker distinguishes these and says which it found.
