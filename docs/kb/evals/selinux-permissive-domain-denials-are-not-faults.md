---
slug: selinux-permissive-domain-denials-are-not-faults
kb_entry: ../errors/os/selinux-permissive-domain-denials-are-not-faults.md
recorded: 2026-08-28
verified_by: rdtroubleshoot os
sources:
  - kind: journal
    path: journalctl -b -g 'avc:.*denied'
---

# Eval fixture — selinux-permissive-domain-denials-are-not-faults

## Input — verbatim evidence

```
AVC avc:  denied  { read } for  pid=1236 comm="bootupctl" name="/" dev="proc" ino=1 scontext=system_u:system_r:bootupd_t:s0 tcontext=system_u:object_r:proc_t:s0 tclass=dir permissive=1
AVC avc:  denied  { read } for  pid=1427 comm="lsblk" name="swaps" dev="proc" ino=4026532100 scontext=system_u:system_r:bootupd_t:s0 tcontext=system_u:object_r:proc_t:s0 tclass=file permissive=1
AVC avc:  denied  { open } for  pid=1427 comm="lsblk" path="/proc/swaps" dev="proc" ino=4026532100 scontext=system_u:system_r:bootupd_t:s0 tcontext=system_u:object_r:proc_t:s0 tclass=file permissive=1
```

## Expected — diagnosis anchor

- **Match:** `selinux-permissive-domain-denials-are-not-faults` via signature
  `journal: avc:\s+denied.*permissive=1`
- **Diagnosis:** the domain is permissive, so these were logged and not enforced. Nothing
  was blocked.
- **Lead action:** none. Ignore them, and look for `permissive=0` if something is actually
  failing.

## Notes

The fixture guards against two opposite errors. Reporting these as faults is the one the
checker actually made — four warnings about a boot that worked. But blanket-ignoring
denials from `lsblk` and `bootupctl` by name would be the mirror mistake: the rule must key
on `permissive=1`, so that the same programs denied in an *enforcing* domain still surface.

A third case that must not match this entry: `getenforce` returning `Permissive`. That is
the whole system unenforced, which is a different (and reportable) state.
