# Error index — cases with a verified fix

Routing table from a distinctive symptom or log line to the entry that handles it. **Scan
this first**; on a miss, scan [`../backlog/INDEX.md`](../backlog/INDEX.md).

One entry usually gets several rows — one per distinct way somebody might describe or paste
the failure. More phrasings routed means higher recall, so add rows freely. Keep each
keyword specific enough to land on exactly one entry; if two failures genuinely share a
surface symptom, consolidate them into one entry with labelled sub-cases rather than adding
two colliding rows.

`rdtroubleshoot kb match <log>` matches the same corpus mechanically, from the
`signatures:` block in each entry. This table is the human-readable half; neither replaces
the other.

| Keyword / signature | Entry |
| --- | --- |
| Switch game loads then shows a black screen, audio works | [ryujinx-black-screen-after-loading](input/ryujinx-black-screen-after-loading.md) |
| `Hid Remap: No matching controllers found` (repeating every 2s, `\|W\|`) | [ryujinx-black-screen-after-loading](input/ryujinx-black-screen-after-loading.md) |
| `Application requests 'ProController, Handheld, JoyconPair'` | [ryujinx-black-screen-after-loading](input/ryujinx-black-screen-after-loading.md) |
| Controller is plugged in and the emulator still does not respond | [ryujinx-black-screen-after-loading](input/ryujinx-black-screen-after-loading.md) |
| Only ~4 shaders compiled and the screen stayed black | [ryujinx-black-screen-after-loading](input/ryujinx-black-screen-after-loading.md) (correlates) |
| Game saves vanish, but the ROM loads fine | [ryujinx-saves-lost-sandbox-home-readonly](flatpak/ryujinx-saves-lost-sandbox-home-readonly.md) |
| `filesystems=home:ro` in an emulator's Flatpak permissions | [ryujinx-saves-lost-sandbox-home-readonly](flatpak/ryujinx-saves-lost-sandbox-home-readonly.md) |
| `reachable read-only via 'home:ro'; writes beside the ROM will fail` | [ryujinx-saves-lost-sandbox-home-readonly](flatpak/ryujinx-saves-lost-sandbox-home-readonly.md) |
| SELinux denials in the journal — are they the problem? | [selinux-permissive-domain-denials-are-not-faults](os/selinux-permissive-domain-denials-are-not-faults.md) |
| `avc: denied ... permissive=1` | [selinux-permissive-domain-denials-are-not-faults](os/selinux-permissive-domain-denials-are-not-faults.md) |
| `comm="lsblk"` / `comm="bootupctl"` denied under `bootupd_t` at every boot | [selinux-permissive-domain-denials-are-not-faults](os/selinux-permissive-domain-denials-are-not-faults.md) |
| SELinux is Enforcing but a denial says `permissive=1` — both true at once | [selinux-permissive-domain-denials-are-not-faults](os/selinux-permissive-domain-denials-are-not-faults.md) |
