---
slug: <slug>
area: <area>
status: open
first_seen: YYYY-MM-DD
last_confirmed: YYYY-MM-DD
signatures:
  - source: symptom
    pattern: <how a person would describe it>
  - source: retrodeck-log
    pattern: <a distinctive log line, as a regex>
    note: <when it appears, and anything that makes it distinctive>
---

# <title naming the symptom>

## TL;DR

We have seen this and there is **no verified fix yet**. <One or two sentences: what
happens, and anything that is known to be safe to try or known not to help. Say plainly
that it is unresolved — a guess offered as a fix is worse than an honest "not yet".>

---

## Engineer notes

### Symptom signature

What the log or the behaviour looks like. Quote the most distinctive lines verbatim — these
are what the signatures above match on.

```
<paste the characteristic lines here>
```

Other tells (timing, emulator, system, which check reports it):

- ...

### What is known

<What has actually been established, and how. Separate observation from inference.>

### What has been ruled out

<As valuable as the findings. "The GPU is initialising correctly, so this is not a driver
problem" stops the next person re-deriving it.>

### Next steps

1. ...

### Sightings

<!-- Newest first. `rdtroubleshoot kb sighting <slug> "..."` appends here and moves
     last_confirmed forward. A second sighting is the cue to investigate and promote. -->

- **YYYY-MM-DD** — first seen. <context: what was being done, which machine, what log>

### Sources

- Log excerpt: `<path, and the timestamp or line range>`
- Checker output: `rdtroubleshoot <group>` — <the relevant lines>
- Upstream issue / discussion: <url>
