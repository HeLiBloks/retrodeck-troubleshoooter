# Contributing

Most contributions here are **knowledge-base entries**: a symptom somebody hit, and — once
it is actually verified — the fix. The tooling handles the mechanics, including deciding
whether you can push directly or need a pull request.

## The short version

```sh
rdtroubleshoot kb search "<your symptom>"     # is it already recorded?
rdtroubleshoot kb match ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/logs/retrodeck.log

# not recorded? file it as an open case
rdtroubleshoot kb new --area <area> --slug <symptom-slug> --title '...'
$EDITOR docs/kb/backlog/<area>/<symptom-slug>.md
$EDITOR docs/kb/backlog/INDEX.md               # add a routing row — required
rdtroubleshoot kb commit <symptom-slug>

# found and verified a fix?
rdtroubleshoot kb promote <symptom-slug> --verified-by "how you confirmed it"
$EDITOR docs/kb/errors/<area>/<symptom-slug>.md   # fill in Fix and Verification
$EDITOR docs/kb/evals/<symptom-slug>.md           # the case that proved it
rdtroubleshoot kb commit <symptom-slug> --push
```

## Direct push or pull request — decided by capability, not by name

`rdtroubleshoot kb commit --push` probes what your credentials can actually do
(`git push --dry-run`, which authenticates and writes nothing):

- **Push access** → it pushes to `main`.
- **No push access** → it moves your work onto a branch `kb/<slug>` and prints the fork-and-PR
  commands. Nothing is lost and nothing is half-pushed.

```sh
gh repo fork --remote --remote-name fork    # once
git push fork kb/<slug>
gh pr create --base main --head kb/<slug> --fill
```

This is deliberately a capability probe rather than a username check, so it works for anyone
without the repository hardcoding who its owner is.

## What gets merged quickly

An entry that is **honest about its own status**. The single most useful thing you can
contribute is a well-recorded *unsolved* case — a `backlog/` entry with a real log excerpt, a
matchable signature, and a clear account of what has been ruled out. Those are cheap to
review and immediately useful, because "known, no fix yet" is a real answer.

What slows a review down is a fix presented as verified when it was only plausible. If you
have not seen the symptom disappear, leave it in `backlog/` and say so — that is not a
lesser contribution.

## The gate

`kb commit` refuses unless `rdtroubleshoot kb check` is clean and the test suite is green.
The lint is not stylistic; each rule stands for a way a knowledge base rots:

- an entry with **no INDEX row** — invisible to anyone searching;
- an `errors/` entry with **no `verified:` / `verified_by:`** — a fix nobody confirmed;
- an entry whose **every signature is `symptom`** — nothing can route to it from a log;
- a **slug that disagrees** with its filename or its directory;
- a signature **pattern that is not valid regex**;
- an `errors/` entry with **no eval fixture** — no record of the case that proved it.

Run `rdtroubleshoot kb gate --skip-tests` for the fast version while drafting.

## Code contributions

Same suite, plus two rules from `CLAUDE.md` that are easy to break by accident:

- **Nothing writes.** No file, no network request, no emulator started. That is what makes
  the tool safe to run while RetroDECK is open, which is when people actually use it. The
  KB write commands are the deliberate exception, and they live behind the gate above.
- **A state is not a fault.** `/` being 100% full on an ostree host, a stopped distrobox, a
  permissive-domain SELinux denial — all normal. A check whose exit code fires on those
  trains its user to ignore it. Report them as `INFO`.
- **Stdlib only.** Enforced by `tests/test_stdlib_only.py`, which reads the AST — an import
  inside a function body is still an import.

Run `./tools/check.sh` (compile + suite + CLI smoke). And run the CLI on a machine *without*
RetroDECK installed too: that is what proves a new check degrades to `INFO` rather than
crashing, and it is how several defects were caught.

## Reporting without contributing an entry

Open an issue with the log excerpt and what you were doing. The signature is the valuable
part — a verbatim line beats a paraphrase, because that is what routes future reports to the
same place.

## Privacy

This repository is public, and its docs quote real diagnostic output. Before committing,
check that no username, host name, LAN address, account name or secret appears — including
in a log excerpt, which is the easy place to miss one. Use `/home/<user>` and a placeholder
host. `.env` is gitignored; `.env_template` ships every key empty.
