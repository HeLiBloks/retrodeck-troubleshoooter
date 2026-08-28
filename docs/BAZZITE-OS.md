# Host troubleshooting: Fedora Atomic, SELinux, Flatpak, Homebrew

The point of this file is knowing which normal-looking alarm on an immutable host is
actually normal. Three of them are, all measured on the test machine rather than assumed, and
each one will otherwise send you looking for a fault that is not there.

## Three things that look broken and are not

### `/` is 100% full, and always will be

```
composefs        45M   45M     0 100% /
```

That is the ostree composefs image — read-only by construction, sized to its content. A
`df` check that does not skip it reports a full disk on a machine with hundreds of GiB free.
`rdtroubleshoot os` skips every pseudo filesystem and says so explicitly.

The writable space is elsewhere: `/var` (and `/var/home`, which is where `$HOME` really
lives) plus whatever volumes are mounted under it.

### SELinux denies sshd a control socket on every connection

```
audit[7352]: AVC avc: denied { create } for pid=7352 comm="sshd-session"
  name="s.<random>.sshd.<random>"
  scontext=system_u:system_r:sshd_session_t:s0-s0:c0.c1023
  tcontext=system_u:object_r:ssh_home_t:s0 tclass=sock_file permissive=0
```

An upstream policy gap hit by SSH connection multiplexing (`ControlMaster`). Nothing to do
with emulation, and it fires on every connection, so it floods `ausearch` and buries
anything real. `rdtroubleshoot os` filters it by default and reports the count;
`--show-benign` shows it.

The filter is a `(comm, tclass, tcontext)` triple, deliberately narrow — a denial from any
other program, class or context still surfaces.

### Homebrew is installed but not on PATH

`/home/linuxbrew/.linuxbrew` exists while `command -v brew` finds nothing under
`ssh host 'cmd'`. The shellenv is sourced from an interactive profile, so a non-interactive
shell — a script, a cron job, an agent session — never sees it. Every
"brew: command not found" in that context is this, not a broken install:

```sh
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
```

## SELinux, when it *is* the problem

Enforcing is the expected state and should stay that way. The failure mode that matters
here is a **mislabelled ROM volume**: a separate disk formatted or populated elsewhere can
come up `unlabeled_t` or `default_t` instead of `user_home_t`, and the symptom is an
emulator that sees an empty folder — no error, no denial the user ever reads.

```sh
ls -Zd ~/retrodeck/roms           # expect ...:user_home_t:s0
sudo restorecon -RFv ~/retrodeck  # relabel if it is not
```

Measured on this machine: `unconfined_u:object_r:user_home_t:s0` throughout, which is
correct. `rdtroubleshoot os` checks it.

To read denials properly when you do suspect policy:

```sh
sudo ausearch -m avc -ts boot | audit2allow -w     # why it was denied, in prose
journalctl -b -g 'avc:.*denied' | tail -40         # works without root for wheel/adm
```

Bisecting with `setenforce 0` is legitimate, but note that `rdtroubleshoot` reports
permissive as a **WARN** precisely because a denial found while permissive is not your bug.
Put it back.

## Fedora Atomic: what you cannot do, and what to do instead

No `dnf install` for tooling. The install paths are:

| want | use |
|---|---|
| a CLI tool | `brew install`, or a distrobox |
| a build toolchain | `distrobox create` + the distro's own package manager |
| a GUI app | Flatpak |
| something that must be in the image | `rpm-ostree install` — needs a reboot, avoid |

**A staged deployment means the running system is not the one on disk.** If something
"worked yesterday", check for a pending update that has been staged but not booted —
`rdtroubleshoot os` reports it as a WARN. `rpm-ostree status`; reboot to apply, or
`rpm-ostree cleanup -p` to discard.

The `skyscraper` distrobox on this machine is an Ubuntu 24.04 container and is normally
**Exited**; that is fine, `distrobox enter` starts it. `~/.skyscraper/` lives in `$HOME`,
which distrobox shares with the host, so config and cache written either side are the same
files.

## Flatpak: the sandbox is the usual culprit

The interesting failure is never "flatpak is broken". It is that an emulator cannot see, or
cannot write, the directory holding the games — and the symptom is an empty system in the
carousel or a save that vanishes, neither of which mentions Flatpak.

```sh
flatpak info --show-permissions net.retrodeck.retrodeck
flatpak override --user --show io.github.ryubing.Ryujinx
rdtroubleshoot flatpak --probe-sandbox    # asks the sandbox itself
```

What each grant means for a ROM tree at `~/retrodeck`:

| `filesystems=` | effect |
|---|---|
| `host` | everything, read-write. RetroDECK has this. |
| `home` | all of `$HOME`, read-write, submounts included |
| `home:ro` | readable, **not writable**. Ryujinx has this — saves beside the ROM fail. |
| `~/retrodeck` | that tree only; a sibling folder is invisible |
| *(absent)* | invisible. This is the empty-carousel case. |

Measured on this machine: RetroDECK has `host` and `devices=all`, so its sandbox is not the
blocker for anything. Ryujinx has `home:ro`. Supermodel has `home;host:ro`.

**The ROM tree is usually its own filesystem.** Here `~/retrodeck` is the whole of
`nvme0n1` (btrfs, label RetroDECK) mounted inside a home on `nvme1n1p3`. A `home` grant
carries the submount along; a grant of some *specific* other `~/subdir` does not.

To widen a grant, and to undo a hand edit:

```sh
flatpak override --user --filesystem=~/retrodeck io.github.ryubing.Ryujinx
flatpak override --user --reset io.github.ryubing.Ryujinx
```

**Overrides are invisible in the manifest.** Flatseal writes to
`~/.local/share/flatpak/overrides/<app>` and `/var/lib/flatpak/overrides/<app>`, and
`flatpak info --show-permissions` folds them in silently — so a permission you cannot
explain from the app's design is usually one that was changed by hand and can be reset.
There is also a `global` file in those directories that applies to every app.

Other Flatpak checks worth a glance: `flatpak list --runtime` for end-of-life runtimes
(`flatpak uninstall --unused`), and `flatpak repair --user` when an install is genuinely
inconsistent.

## Controllers and udev

`/dev/input/event*` is `root:input` mode `660`, and the seated desktop user gets access
through a **POSIX ACL** that udev's `uaccess` tag grants — not through group membership.

The consequence for anyone debugging over SSH: an SSH session is not on that seat, so
`getfacl /dev/input/event0` correctly shows no entry for you while the desktop session has
one. `rdtroubleshoot input` reports unreadable nodes as **INFO** for that reason, and says
so. Check from the desktop session before changing anything; `usermod -aG input $USER` is
the blunt fix and is rarely the right one.

`joydev` must be loaded for `/dev/input/js*` to exist at all. No `js*` node and no
`hid_playstation`/`hid_sony`/`xpad` in `lsmod` means no pad is connected — which, per
[EMULATION.md](EMULATION.md), is the black-screen case.

## This machine

- **Lenovo IdeaPad Gaming 3 15ARH05**, hostname `the test machine`, Bazzite 44
  (Kinoite), Ryzen 5 4600H, 48 GB DDR4, GTX 1650 Ti Mobile, 12 cores.
- **Two disks, and the labels are the reliable way to tell them apart** — `lsblk` measured
  2026-08-28:
  - `nvme0n1` — the larger disk, btrfs, label **RetroDECK**, **whole device with no
    partition table**, mounted at `~/retrodeck`.
  - `nvme1n1p3` — the smaller disk, btrfs, label **bazzite**, carrying `/var`, `/var/home`,
    `/sysroot` and `/etc`. `nvme1n1p2` is `/boot`.
  - The device numbering is not what you would guess, which is the whole point of the note
    below: go by the label.
  - **Neither is LUKS**; there is no dm-crypt device on the box at all.
  - Note that this is the reverse of what an older note in the scraper's CLAUDE.md claimed
    ("ROM library is nvme1n1 … OS/home is nvme0n1p3"). `rdtroubleshoot os` reports the live
    topology rather than asserting either version, which is why the discrepancy surfaced.
- **RetroDECK** is a **system** Flatpak, `net.retrodeck.retrodeck` 0.10.9b, using the
  `~/retrodeck/ES-DE/` layout.
- `$HOME` is `/home/retro`, a symlink to `/var/home/retro`. See the path-prefix trap in
  [EMULATION.md](EMULATION.md).
- SSH from the dev machine: `ssh -o BatchMode=yes retro@retrodeck-box`. Do **not** use
  SSH's `-b` or set `BindAddress`; let routing pick the source address. Same rule for `scp`
  and `rsync`.
