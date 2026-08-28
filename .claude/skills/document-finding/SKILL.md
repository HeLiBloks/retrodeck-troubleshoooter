---
name: document-finding
description: Record a troubleshooting finding in the knowledge base and commit it - file an open case, add a sighting, or promote a verified fix and push it. Use after diagnosing something that was not already recorded, and whenever a fix has been confirmed to work.
---

# Documenting a finding

The point of this repository is that a problem solved once stays solved. That only works if
the finding is written down while it is fresh, with the evidence attached — so this runs at
the *end* of every troubleshooting session that learned something, not only the ones that
found a fix.

Run the `kb-lookup` pre-flight first. If the symptom was already recorded, the work here is
a sighting, not a new entry.

## Decide which of three things happened

| what happened | do this |
|---|---|
| Known symptom recurred | `kb sighting <slug> "..."` — commit |
| New symptom, **no fix yet** | `kb new` → fill in → INDEX row → commit |
| Fix found **and confirmed** | `kb promote --verified-by ...` → fill in → commit `--push` |
| Normal-and-permanent, not a fault | append to `docs/kb/backlog/_skipped.md` with a review date |

A new symptom is **always** born in `backlog/`, even when you think you know the fix. It
reaches `errors/` only by promotion, and promotion needs verification.

## Filing an open case

```sh
rdtroubleshoot kb new --area <os|flatpak|emulation|input|scraping> \
  --slug <symptom-slug> --title '<what the user sees>'
```

Then fill the file in. Four things carry the value:

1. **Signatures.** At least one non-`symptom` source, or nothing can ever route to this entry
   from a log. Take the pattern from a **verbatim** log line, not a paraphrase, and check it
   is valid regex — the lint will tell you.
2. **The symptom signature block.** Paste the real lines. This is what the next person greps.
3. **What is known, separated from what is guessed.** Established facts and how they were
   established; hypotheses under `Next steps` where they are visibly hypotheses.
4. **What has been ruled out.** As valuable as the findings, and the thing most often
   omitted.

Add the routing row to `docs/kb/backlog/INDEX.md` — several rows if the symptom can be
described several ways. **An entry with no INDEX row is invisible**, and the lint fails on it.

The slug names the **dominant symptom, not the cause**. Causes get re-diagnosed; symptoms are
what somebody greps for a year later.

## Promoting a verified fix

Three things must be true, and you must be able to say which is which:

1. the symptom was **observed**;
2. the fix was **applied**;
3. the symptom was then **confirmed gone**.

"It should work" is not verification. Neither is "the command exited 0". If you have not seen
the symptom disappear, **leave it in `backlog/`** and record what you tried — that is a
useful contribution, and a fix presented as verified when it was only plausible is the one
thing this structure exists to prevent.

```sh
rdtroubleshoot kb promote <slug> --verified-by "the game drew its title screen after the pad was bound"
```

That stamps `verified:` / `verified_by:`, moves the file and its INDEX rows into `errors/`,
and scaffolds `docs/kb/evals/<slug>.md`. Then fill in:

- the **TL;DR** — rewrite it completely. It is no longer "known, no fix"; it is the action,
  first, in two or three sentences.
- **`### Fix`** and **`### Verification`** — the latter says what was *seen*, not what was run.
- **`### When this entry does not fit`** — what signal means the diagnosis is wrong. An entry
  that cannot be falsified will be trusted past its usefulness.
- the **eval fixture** — the verbatim evidence and the expected diagnosis. Note any red
  herring it has to see past; that is what makes a fixture worth keeping.

## Committing and pushing

```sh
rdtroubleshoot kb check                    # the lint
rdtroubleshoot kb commit <slug>            # evidence: commit it
rdtroubleshoot kb commit <slug> --push     # a verified fix: commit and publish
```

`kb commit` refuses unless the lint is clean and the suite is green, and it builds the commit
message from the entry itself. `--push` probes whether the credentials can push: with access
it pushes to `main`, without it moves the work to a branch `kb/<slug>` and prints the
fork-and-PR commands.

**Push a fix; do not push a guess.** Committing evidence is free — an observation that turns
out to be incomplete costs a later correction. Publishing a fix tells the next person to *do*
something, so the gate above is the whole point. If the gate blocks, read the reasons and fix
them; do not reach for `--skip-tests` to get past it.

## Before you commit, on a public repository

The docs quote real diagnostic output, and a log excerpt is the easy place to leak a
username, a host name or a LAN address. Check the diff, not just your intent. Use
`/home/<user>` and a placeholder host.
