---
name: diagnose-host
description: Diagnose host-level blockers on Bazzite or another Fedora Atomic system - SELinux denials and mislabelled volumes, Flatpak sandbox permissions and overrides, a staged ostree deployment, Homebrew not on PATH, distrobox state, disk space. Use when something is denied, invisible, or read-only rather than merely misconfigured.
---

# Diagnosing a host-level blocker

Immutable Fedora is full of states that look like faults. Before investigating anything,
know these three, all measured on this machine:

- **`/` is 100% full and always will be** — it is a 45 MB read-only composefs image. The
  machine has hundreds of GiB free elsewhere.
- **SELinux denies sshd a control socket on every connection.** An upstream policy gap hit
  by SSH multiplexing; nothing to do with emulation, and it buries real denials.
- **Homebrew is installed but not on PATH in a non-interactive shell.** Every
  "brew: command not found" from a script or an agent session is this.

## 1. Always start here

```sh
./rdtroubleshoot os flatpak
./rdtroubleshoot os --show-benign      # include the known-benign SELinux denials
./rdtroubleshoot env                   # is a .env supplying the privileged checks?
```

Two checks need root and are skipped without one: the full SELinux **audit log** (the
journal mirrors most AVC records but can drop them), and **system Flatpak overrides** under
`/var/lib/flatpak`. Both print the command to run by hand. If the user has a `.env` with
`RDT_SUDO_PASSWORD`, they run automatically — do **not** ask for a password, and do not put
one on a command line.

## 2. Match the symptom

| symptom | check |
|---|---|
| an app sees an **empty folder** | Flatpak `filesystems=` grant, then the SELinux label |
| writes fail, reads work | a `:ro` grant, or a read-only mount |
| "it worked yesterday" | a **staged ostree deployment** that has not been booted |
| `brew: command not found` in a script | shellenv not sourced; not a broken install |
| a denial in the journal | is it in the benign list? then `audit2why` |
| `dnf install` refused | expected — use brew, distrobox, or Flatpak |
| a full disk | check *which* filesystem; ignore composefs and the ESP |

## 3. Flatpak sandbox

The interesting failure is an emulator that cannot see or cannot write the ROM tree — which
presents as an empty carousel or a vanishing save, never as a Flatpak error.

```sh
flatpak info --show-permissions net.retrodeck.retrodeck
flatpak override --user --show io.github.ryubing.Ryujinx
./rdtroubleshoot flatpak --probe-sandbox     # asks the sandbox itself; slower
```

`--probe-sandbox` runs `sh` inside the app's own runtime. It starts no emulator and writes
nothing, but it is ground truth where the static analysis of `filesystems=` is a model.

Two things that mislead here: the ROM tree is usually **its own filesystem** mounted under
`$HOME`, and **overrides are folded into `--show-permissions` invisibly**, so a grant you
cannot explain from the app's design was probably set by hand (Flatseal) and can be
`--reset`.

## 4. SELinux

Enforcing is correct and should stay that way. The failure that matters is a **mislabelled
volume** — a disk populated elsewhere coming up `unlabeled_t` instead of `user_home_t`, with
no error the user ever sees:

```sh
ls -Zd ~/retrodeck/roms              # expect ...:user_home_t:s0
sudo restorecon -RFv ~/retrodeck
sudo ausearch -m avc -ts boot | audit2allow -w
```

`setenforce 0` is a legitimate bisection step, but a denial found while permissive is not
your bug. Put it back, and say in your report that you did.

## 5. Rules

- **Read before you change.** Everything in `rdtroubleshoot` is read-only; keep the
  diagnosis and the fix as separate, stated steps.
- **Prefer `--user` overrides** over system ones, and name the exact command you ran so it
  can be reset.
- **Never widen a sandbox to `host` to make a symptom go away** — grant the specific path.
- **Do not layer packages with `rpm-ostree`** to get a tool; that needs a reboot and changes
  the image. Use brew or a distrobox.
- Confirm before anything that reboots, relabels a whole volume, or resets someone's
  overrides.

Full background: [docs/BAZZITE-OS.md](../../../docs/BAZZITE-OS.md).
