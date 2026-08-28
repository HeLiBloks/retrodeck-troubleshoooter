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
