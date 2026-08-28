---
slug: selinux-permissive-domain-denials-are-not-faults
area: os
status: fixed
first_seen: 2026-08-28
last_confirmed: 2026-08-28
verified: 2026-08-28
verified_by: rdtroubleshoot os reports these as INFO and "no unexplained enforced denials this boot"; the boot they came from completed normally
signatures:
  - source: symptom
    pattern: selinux (denial|denied|avc).*(should i|is this|problem|worry)
  - source: journal
    pattern: avc:\s+denied.*permissive=1
    note: the permissive=1 field is the whole answer — nothing was blocked
  - source: journal
    pattern: comm="(lsblk|bootupctl)".*scontext=\S*bootupd_t
    note: this platform ships bootupd_t permissive; fires at every boot
---

# SELinux denials in the journal that blocked nothing (`permissive=1`)

## TL;DR

**Not your problem.** A denial whose record ends `permissive=1` was *logged and not
enforced* — the domain is permissive, so nothing was blocked and nothing broke. This
platform ships `bootupd_t` that way, so `lsblk` gets denied a read on `/proc/swaps` at
every single boot. `rdtroubleshoot os` separates these out and reports them as a note.
Only a denial with `permissive=0` can have caused a failure.

---

## Engineer notes

### Symptom signature

```
AVC avc:  denied  { open } for  pid=1427 comm="lsblk" path="/proc/swaps" dev="proc"
  ino=4026532100 scontext=system_u:system_r:bootupd_t:s0
  tcontext=system_u:object_r:proc_t:s0 tclass=file permissive=1
```

Other tells:

- `permissive=1` on the record while `getenforce` says **Enforcing** — the *domain* is
  permissive, not the system. Both can be true at once and usually are.
- On this platform the recurring set is `bootupctl` (1x) and `lsblk` (3x) per boot, all in
  `bootupd_t`, all reading under `/proc`.
- They fire at boot, from pids in the low thousands — before anything the user did.

### Cause

SELinux supports per-domain permissive mode: a domain marked permissive logs what it would
have denied and allows it anyway. That is how a policy is developed without breaking the
system. `bootupd` (the bootloader updater) ships that way here, and its helper invocations
of `lsblk` legitimately read `/proc` paths the policy has not been extended to cover.

### Diagnosis steps

1. `rdtroubleshoot os` — permissive denials collapse into one INFO line with counts;
   enforced ones are reported individually as WARN.
2. To read them by hand, the field is the whole answer:
   ```sh
   journalctl -b -g 'avc:.*denied' | grep -c 'permissive=1'   # blocked nothing
   journalctl -b -g 'avc:.*denied' | grep -c 'permissive=0'   # could have blocked something
   ```
3. For an enforced denial, get the explanation in prose:
   ```sh
   sudo ausearch -m avc -ts boot | audit2allow -w
   ```

### Fix

None needed — this is the platform working as designed. **Do not** `setenforce 0` on
account of it, and do not write a policy module to silence it: an allow rule for a
permissive domain changes nothing about what runs and only makes the next real denial
harder to spot.

If the noise is the problem rather than the denial, `rdtroubleshoot os` already filters it;
`--show-benign` shows everything.

### Verification

The boot these denials came from completed normally, `bootupd` did its work, and
`rdtroubleshoot os` reports `no unexplained enforced denials this boot` alongside the note.
The checker was built by reading the field: before it did, these were four WARN lines about
a boot that had worked.

### When this entry does not fit

- The record says **`permissive=0`** — that denial *was* enforced and something really was
  blocked. Chase it with `audit2why`.
- `getenforce` says `Permissive` — then the whole system is unenforced, and *no* denial
  found while in that state is evidence of your bug. Put it back with `setenforce 1`.
- The denying process is an emulator, RetroDECK, or anything touching the ROM tree — that is
  worth reading regardless of the flag, because a mislabelled ROM volume presents as an
  emulator seeing an empty folder with no error the user ever reads.

### Sightings

- **2026-08-28** — 4 permissive denials per boot on the test machine (`lsblk` 3, `bootupctl`
  1), alongside ~50 enforced-but-benign sshd control-socket denials. Found while building
  the `os` checks, which had reported the permissive ones as warnings.

### Sources

- Checker output: `rdtroubleshoot os --show-benign`
- Eval fixture: `../../evals/selinux-permissive-domain-denials-are-not-faults.md`
- Background: [docs/BAZZITE-OS.md](../../../BAZZITE-OS.md) § "Three things that look broken and are not"
