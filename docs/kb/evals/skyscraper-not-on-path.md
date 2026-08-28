---
slug: skyscraper-not-on-path
kb_entry: ../errors/scraping/skyscraper-not-on-path.md
recorded: 2026-08-28
verified_by: command -v Skyscraper resolves from a fresh non-interactive SSH shell
sources:
  - kind: checker
    command: rdtroubleshoot scraping
---

# Eval fixture — skyscraper-not-on-path

## Input — verbatim evidence

```
WARN  Skyscraper  not on PATH but present at /home/<user>/skysource/Skyscraper
                  -> export PATH="/home/<user>/skysource:$PATH"
```

```
$ ssh host 'command -v Skyscraper || echo NOT-ON-PATH'
NOT-ON-PATH
$ ssh host "bash -lic 'command -v Skyscraper || echo NOT-ON-PATH-INTERACTIVE'"
NOT-ON-PATH-INTERACTIVE
```

## Expected — diagnosis anchor

- **Match:** `skyscraper-not-on-path` via signature `checker: Skyscraper`
- **Diagnosis:** the binary exists and nothing puts its directory on `PATH`, in either an
  interactive or a non-interactive shell. Only `gather`, `scrape` and `generate` need it.
- **Lead action:** symlink into `~/.local/bin`, and add that directory to `PATH` **above**
  the non-interactive guard in `~/.bashrc`.

## Notes

Kept for the **wrong hypothesis**, which is the instructive part. The obvious cause is the
interactive/non-interactive `PATH` split, and that split is genuinely real on this machine —
Homebrew is on the interactive `PATH` and absent from the non-interactive one. It is not the
cause here: Skyscraper is missing from **both**.

The test that appeared to confirm it had exported `PATH` in the parent shell and then run
`bash -lic` in the same script, so the child inherited the export. **A PATH test is only
valid in a shell that has not been touched.** A fixture that only carried the correct
answer would not protect against re-deriving that mistake.

The second near-miss: the stopped `skyscraper` distrobox looks like a candidate and is not
one — `Exited` is its normal resting state between uses.
