# Skipped candidates

Append-only ledger of symptoms that were looked at and **deliberately not filed**, with the
reason and a review date. It exists so the same non-case is not re-investigated from scratch
every time it appears, and so a decision to skip is visible rather than implicit.

A skip is not permanent. When the review date passes, or the symptom recurs, or new evidence
arrives, the entry moves to `backlog/` like anything else — the date is a prompt to look
again, not a verdict.

Consulted by the dedup pre-flight alongside `errors/INDEX.md` and `backlog/INDEX.md`.

| Date | Symptom | Why skipped | Review after |
| --- | --- | --- | --- |
| 2026-08-28 | `/` reports 100% full on an ostree host | Normal and permanent — a read-only composefs image sized to its content. Documented in `docs/BAZZITE-OS.md` and filtered by `rdtroubleshoot os`; it is not a fault and never will be. | never |
| 2026-08-28 | `brew: command not found` in a script or agent session | Not a fault: Homebrew is installed and its shellenv is only sourced from an interactive profile. `rdtroubleshoot os` reports it as a note with the `shellenv` line. | never |
| 2026-08-28 | sshd denied a `sock_file` in `ssh_home_t` on every SSH connection | Enforced but benign — an upstream policy gap hit by connection multiplexing, unrelated to emulation. Filtered by default on a `(comm, tclass, tcontext)` triple so anything else still surfaces. | 2027-02-28 |
| 2026-08-28 | `[ERROR] setReportingLevelFromRetroDeckConfig: Failed to read rd_logging_level - RETRODECK_CONFIG_HOME environment variable not set. Falling back to DEBUG.` | RetroDECK's own startup quirk, not a fault in anything here: the variable is unset when ES-DE reads it, so logging falls back to DEBUG. Consequence is verbosity only — 8430 of one log's 8678 lines were DEBUG, giving a 1.5 MB log. Nothing misbehaves. Filed as skipped rather than as a case because the fix belongs upstream in RetroDECK. | 2027-02-28 |
| 2026-08-28 | `Import rule configuration contains invalid system "steam"` / `"lutris"` / `"epic"` / `"emulators"` | Not a fault: ES-DE ships import rules for launcher integrations this install does not use, and warns once per unknown system at startup. Four lines, no effect. | never |
| 2026-08-28 | `Unknown platform "portmaster" defined for system "portmaster", scraper searches will be inaccurate` | Correct and expected — `portmaster` is a RetroDECK custom system with no upstream scraper platform, and the scraper deliberately excludes it. The warning describes a real limitation that nobody intends to fix. | never |
| 2026-08-28 | `File "X" does not exist, skipping entry` (5 paths) | Stale gamelist entries for files that were removed — dragon32, one neogeo romset, a PortMaster launcher, a DOS installer folder. ES-DE skips them harmlessly and they clear on the next gamelist write. Reported as INFO by the checker rather than filed, since there is nothing to diagnose. | never |
