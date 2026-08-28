---
slug: skyscraper-not-on-path
area: scraping
status: open
first_seen: 2026-08-28
last_confirmed: 2026-08-28
signatures:
  - source: symptom
    pattern: (skyscraper|gather|generate).*(not found|command not found|won'?t run|cannot run)
  - source: checker
    pattern: Skyscraper
    note: the check names where the binary is, if it can find it at all
---

# Skyscraper is installed but not on PATH, so gather and generate cannot run

## TL;DR

We have seen this and there is **no fix recorded yet** — only workarounds, and which one is
right depends on how the machine is meant to invoke it. The binary exists at
`~/skysource/Skyscraper` and is not on `PATH` in **either** an interactive or a
non-interactive shell, so anything that shells out to `Skyscraper` fails. The offline
half of scraping (`enrich`, `status`, `missing`, `dedupe`) is unaffected; only `gather`,
`scrape` and `generate` need the binary.

---

## Engineer notes

### Symptom signature

```
WARN  Skyscraper  not on PATH but present at /home/<user>/skysource/Skyscraper
                  -> export PATH="/home/<user>/skysource:$PATH"
```

Other tells:

- `command -v Skyscraper` finds nothing, while the file is present and executable.
- Running it by absolute path works and prints its banner, so the binary itself is fine.
- A `skyscraper` distrobox container exists but is `Exited` — which is a normal resting
  state, not a fault.

### What is known

- The binary is present, executable, and runs: invoking it by absolute path prints the
  version banner.
- It is absent from `PATH` in a **non-interactive** shell (`ssh host 'command -v Skyscraper'`)
  **and** in an **interactive login** shell (`ssh host "bash -lic 'command -v Skyscraper'"`).
  No profile file under `~` mentions `skysource`, so nothing ever adds it.
- There are two working invocation routes and it is not obvious which the machine should
  standardise on: the host binary at `~/skysource/Skyscraper`, or `distrobox enter -n
  skyscraper -- Skyscraper`, which is how it was built.

### What has been ruled out

- **Not a broken build.** It runs and reports its version.
- **Not the interactive/non-interactive PATH split**, which was the first hypothesis and is
  wrong. That split is real on this machine — Homebrew is on the interactive `PATH`
  (`/home/linuxbrew/.linuxbrew/bin`) and absent from the non-interactive one — so it was a
  plausible cause. It is not this one: Skyscraper is missing from both.
  - Worth recording *how* that was nearly recorded as fact: the first test exported
    `PATH` in the parent shell and then ran `bash -lic` in the same script, so the child
    inherited the export and appeared to find it. **A PATH test is only valid in a shell
    that has not been touched.**
- **Not the stopped distrobox.** `Exited` is the normal state between uses; `distrobox
  enter` starts it.

### Next steps

1. Decide which invocation route is canonical for this machine — host binary or distrobox.
   That is a setup decision, not a diagnosis, which is why this entry has no fix yet.
2. Whichever is chosen, make it durable rather than a per-shell `export`: a line in the
   shell profile, or a wrapper on `PATH`. A workaround that has to be retyped will be
   forgotten in exactly the unattended run that needs it.
3. Consider whether the checker should distinguish "absent from a non-interactive shell
   only" from "absent everywhere" — the two have different fixes, and the current WARN
   reads the same for both.

### Sightings

- **2026-08-28** — found by `rdtroubleshoot scraping` on the test machine, one of only two
  real warnings across the whole library. Not a user report: nothing had needed `gather`
  recently, which is why it had gone unnoticed.

### Sources

- Checker output: `rdtroubleshoot scraping`
- Background: [docs/SCRAPING.md](../../../SCRAPING.md) § "Skyscraper's two phases, and which one costs quota"
