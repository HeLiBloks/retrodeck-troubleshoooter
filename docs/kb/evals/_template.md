---
slug: <slug>
kb_entry: ../errors/<area>/<slug>.md
recorded: YYYY-MM-DD
verified_by: <verified_by>
sources:
  - kind: log
    path: <the log this was taken from>
  - kind: checker
    command: rdtroubleshoot <group>
---

# Eval fixture — <slug>

A recorded case that this entry's diagnosis must keep getting right. Two purposes: it is
the stable record of what the problem actually looked like, and it is a regression check —
replay the input and confirm the diagnosis still lands.

## Input — verbatim evidence

```
<the log lines, checker output, or the question as the user actually asked it>
```

## Expected — diagnosis anchor

- **Match:** `<slug>` via signature `<source>: <pattern>`
- **Diagnosis:** <one line, mirroring the entry's cause>
- **Lead action:** <the first thing the TL;DR tells the user to do>

## Notes

<Anything that made this case a good fixture — a near-miss with another entry, a red
herring it has to see past.>
