---
slug: skyscraper-not-on-path
area: scraping
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: command -v Skyscraper resolves and --version runs from a fresh non-interactive SSH shell
signatures:
  - source: symptom
    pattern: (skyscraper|gather|generate).*(not found|command not found|won'?t run|cannot run)
  - source: checker
    pattern: Skyscraper
    note: the check names where the binary is, if it can find it at all
---

# Skyscraper is installed but not on PATH, so gather and generate cannot run

## TL;DR

Symlink the binary into `~/.local/bin` and make sure that directory is on `PATH` for
non-interactive shells too:

```sh
ln -sfn ~/skysource/Skyscraper ~/.local/bin/Skyscraper
```

If `command -v Skyscraper` still finds nothing over `ssh host 'cmd'`, `~/.local/bin` is not
on the non-interactive `PATH` — see the fix below, which adds it *above* the guard in
`~/.bashrc` that returns early for non-interactive shells. Only `gather`, `scrape` and
`generate` need the binary; the offline half (`enrich`, `status`, `missing`, `dedupe`) works
without it.

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

### Fix

A symlink plus a `PATH` entry, both durable. A per-shell `export` is not a fix: it will be
forgotten in exactly the unattended run that needs it.

1. **Symlink the binary** into the standard user bin directory. Verified safe — Skyscraper
   reads its configuration and cache from `~/.skyscraper/`, not from its own directory, so
   it runs correctly from a symlink:
   ```sh
   mkdir -p ~/.local/bin
   ln -sfn ~/skysource/Skyscraper ~/.local/bin/Skyscraper
   ```
2. **Put `~/.local/bin` on the non-interactive `PATH`.** This is the half that is easy to
   get wrong. Fedora's shipped `~/.bashrc` opens with

   ```sh
   # If not running interactively, don't do anything
   case $- in
       *i*) ;;
         *) return;;
   esac
   ```

   Bash *does* read `~/.bashrc` for `ssh host 'cmd'` (it detects stdin is a socket), but
   that guard returns before anything below it runs. So the `PATH` block has to go **above
   the guard**:

   ```sh
   case ":$PATH:" in
     *":$HOME/.local/bin:"*) ;;
     *) PATH="$HOME/.local/bin:$PATH" ;;
   esac
   export PATH
   ```

   Idempotent, so re-sourcing does not stack duplicates. Back the file up first.

The distrobox route (`distrobox enter -n skyscraper -- Skyscraper`) remains available and
needs no `PATH` change; it is the right choice if the host binary is ever rebuilt against
libraries the host lacks.

### Verification

From a **fresh** SSH session, which is the case that was failing:

```
$ ssh host 'command -v Skyscraper && Skyscraper --version | head -1'
/home/<user>/.local/bin/Skyscraper
Skyscraper  _______ __ ...
```

`rdtroubleshoot scraping` moves from `WARN not on PATH but present at ...` to
`PASS ~/.local/bin/Skyscraper`.

**Test the PATH from a shell that has not been touched.** The first attempt at diagnosing
this exported `PATH` in a parent shell and then ran `bash -lic` in the same script, so the
child inherited the export and appeared to find the binary — see *What has been ruled out*.

### When this entry does not fit

- `command -v Skyscraper` resolves but the binary fails to start — that is a library or
  build problem, not `PATH`. Try the distrobox route.
- The symlink resolves interactively and not over SSH — the `PATH` block is below the
  guard, or in a file a non-interactive shell never reads (`~/.bash_profile`, `~/.profile`).

### Sightings

- **2026-08-28** — found by `rdtroubleshoot scraping` on the test machine, one of only two
  real warnings across the whole library. Not a user report: nothing had needed `gather`
  recently, which is why it had gone unnoticed.

### Sources

- Checker output: `rdtroubleshoot scraping`
- Background: [docs/SCRAPING.md](../../../SCRAPING.md) § "Skyscraper's two phases, and which one costs quota"
