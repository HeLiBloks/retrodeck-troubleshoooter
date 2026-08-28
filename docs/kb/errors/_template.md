---
slug: <slug>
area: <area>
status: fixed
first_seen: YYYY-MM-DD
last_confirmed: YYYY-MM-DD
verified: YYYY-MM-DD
verified_by: <how the fix was confirmed — a check name, a command, or an observation>
signatures:
  - source: symptom
    pattern: <how a person would describe it>
  - source: retrodeck-log
    pattern: <a distinctive log line, as a regex>
    note: <when it appears, and anything that makes it distinctive>
---

# <title naming the symptom>

<!-- Header fields above are the complete set. If a new one is genuinely warranted, add it
     to this template in the SAME commit so every entry stays consistent. -->

## TL;DR

<Two or three sentences. **Action first.** Optionally one quoted line that uniquely
identifies the match. Say what is outside the user's control if anything is. No cause, no
internals, no file paths from inside a sandbox — that is what the engineer half is for.>

---

## Engineer notes

### Symptom signature

```
<the characteristic lines, verbatim>
```

Other tells:

- ...

### Cause

<One or two sentences. Why it happens, not just what to type.>

### Diagnosis steps

1. ...

### Fix

1. ...

### Verification

<How anyone knew it worked — this is what `verified_by` names. State what was observed
after the fix, not just that it was applied. "The check now passes" needs the check named;
"the game runs" needs to say what was seen.>

### When this entry does not fit

<What signal means the diagnosis is wrong and someone should look again. An entry that
cannot be falsified will be trusted past its usefulness.>

### Sightings

- **YYYY-MM-DD** — <context>

### Sources

- Log excerpt: `<path>`
- Checker output: `rdtroubleshoot <group>`
- Eval fixture: `../../evals/<slug>.md`
