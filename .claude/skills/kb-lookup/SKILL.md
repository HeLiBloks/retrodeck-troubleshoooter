---
name: kb-lookup
description: Check the knowledge base before diagnosing anything - the dedup pre-flight. Use at the START of any troubleshooting request, and whenever a symptom, log line, or check failure needs to be matched against what is already recorded.
---

# The dedup pre-flight

**Do this before diagnosing.** Re-investigating a symptom that is already recorded is the
most common waste available, and it is entirely avoidable. It also costs almost nothing:
three commands, no network, no log pull.

## The three lookups

```sh
rdtroubleshoot kb search "<the user's words>"        # slug, title, TL;DR, signatures
rdtroubleshoot kb match <log>                        # route a log to entries mechanically
rdtroubleshoot --kb                                  # annotate each WARN/FAIL with its entries
```

`kb match` takes `--source journal|bios-log|gamelist|ryujinx-config|checker`, or `-` for
stdin. Also grep the two routing tables directly when the phrasing is unusual —
`docs/kb/errors/INDEX.md` **first**, then `docs/kb/backlog/INDEX.md`.

And check `docs/kb/backlog/_skipped.md`: it records symptoms deliberately *not* filed because
they are normal and permanent. A hit there means the answer is "that is not a fault", which
is a complete answer.

## What each outcome means

| outcome | what to do |
|---|---|
| hit in `errors/` | **Answer from the TL;DR half only.** Cross the `---` divider into the engineer notes only if asked why. No commit needed — the entry already exists. |
| hit in `backlog/` | Say plainly: known, no fix yet. Report what has been ruled out, so the user knows what not to retry. Then record a sighting (below) — that is the part that matters. |
| hit in `_skipped.md` | Explain why it is normal. Do not open a case. |
| no hit | Now diagnose. If it turns out to be real and unrecorded, it becomes a new entry — see the `document-finding` skill. |

## Record the sighting

On a `backlog/` hit, a recurrence is the most valuable thing you can add, because **the
second sighting is the cue to go and fix it**:

```sh
rdtroubleshoot kb sighting <slug> "what was seen, where, and on which machine"
```

That moves `last_confirmed` forward and appends a dated line. Commit it — a sighting is an
observation, so it needs no verification gate.

## Two failure modes to avoid

**Do not guess between candidates.** If several entries fit the same surface symptom, name
all of them and say what would distinguish them — then go and check. Picking the
most-likely-looking one and presenting it as the answer is how a knowledge base starts
teaching people the wrong thing.

**Do not treat a near-match as a match.** An entry for a similar symptom in a different
subsystem is a lead, not a diagnosis. If it is genuinely a new case, file it as one; a
duplicate is cheap to merge later, while a wrong sighting on an existing entry corrupts the
record of what that entry covers.
