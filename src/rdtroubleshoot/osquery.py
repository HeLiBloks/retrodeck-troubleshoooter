"""Host-level checks: SELinux, the immutable root, disks, and the tool paths.

The whole value of this group is knowing which of these normal-looking alarms is
actually normal on Fedora Atomic. Three of them are, and all three were measured on
the test machine rather than assumed:

- **`/` is 100% full and always will be.** It is a 45 MB composefs image, read-only by
  construction. A `df` check that does not skip it reports a full disk on a machine with
  hundreds of GiB free.
- **SELinux denies sshd a control socket on every connection.** `sshd_session_t` creating
  a `sock_file` in `ssh_home_t` is an upstream policy gap hit by SSH multiplexing, not
  anything to do with emulation. It floods `ausearch`, so it is filtered by default.
- **Homebrew is installed but not on PATH in a non-interactive shell.** `/home/linuxbrew/.linuxbrew`
  exists while `command -v brew` finds nothing over `ssh host 'cmd'`, because the shellenv
  is sourced from an interactive profile. Every "brew: command not found" in a script or
  an agent session is this and not a broken install.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from .probe import Check, Report, have, human, run

# Denials that are normal on this machine and drown out anything real. Each is a
# (comm, tclass, tcontext-fragment) triple so the filter cannot swallow a whole class.
BENIGN_DENIALS: tuple[tuple[str, str, str], ...] = (
    # SSH multiplexing control socket; fires on every connection, unrelated to emulation.
    ("sshd-session", "sock_file", "ssh_home_t"),
    ("sshd", "sock_file", "ssh_home_t"),
)

# A composefs or other pseudo filesystem being full is meaningless.
PSEUDO_FSTYPES = frozenset(
    {"composefs", "overlay", "tmpfs", "devtmpfs", "squashfs", "erofs", "ramfs", "autofs"}
)
MIN_FREE_BYTES = 20 * 1024**3
LOW_FREE_BYTES = 60 * 1024**3


def _selinux_mode() -> Check:
    result = run(["getenforce"])
    if result is None:
        if not Path("/sys/fs/selinux").exists():
            return Check("INFO", "SELinux", "not enabled on this host")
        return Check("WARN", "SELinux", "selinuxfs is mounted but getenforce is unavailable")
    mode = result.text
    if mode == "Enforcing":
        return Check("PASS", "SELinux", "enforcing (the expected state on Bazzite)")
    if mode == "Permissive":
        return Check(
            "WARN",
            "SELinux",
            "permissive - denials are logged but not blocked, so a denial here is not your bug",
            "setenforce 1 to restore enforcement once you are done bisecting",
        )
    if mode == "Disabled":
        return Check("WARN", "SELinux", "disabled; policy problems cannot be the cause of anything")
    return Check("INFO", "SELinux", f"getenforce says {mode!r}")


def _is_benign(comm: str, tclass: str, tcontext: str) -> bool:
    return any(
        comm == b_comm and tclass == b_class and b_ctx in tcontext
        for b_comm, b_class, b_ctx in BENIGN_DENIALS
    )


_AVC_RE = re.compile(
    r"avc:\s+denied\s+\{(?P<perms>[^}]*)\}.*?"
    r'comm="(?P<comm>[^"]*)".*?'
    r"tcontext=(?P<tcontext>\S+)\s+tclass=(?P<tclass>\S+)"
    r"(?:.*?permissive=(?P<permissive>[01]))?"
)


def _selinux_denials(*, show_benign: bool = False) -> list[Check]:
    """AVC denials this boot, with the ones that blocked nothing separated out.

    Reads the journal rather than `ausearch`, because `ausearch` needs root to read
    /var/log/audit while the journal carries the same AVC records for a user in the
    `wheel`/`adm` set.

    Two kinds of denial are set aside:

    - **`permissive=1` means the denial was logged and not enforced**, because the domain
      is a permissive one. Nothing was blocked, so nothing broke. Bazzite ships
      `bootupd_t` permissive and it denies `lsblk` a read on `/proc/swaps` at every boot;
      reported as a fault that is three warnings about a boot that worked. This is a
      general rule rather than a list of programs, which is why it is preferred to adding
      those to BENIGN_DENIALS.
    - the known-benign triples above, which are enforced but understood.
    """
    result = run(["journalctl", "--no-pager", "-b", "-g", "avc:.*denied", "-o", "cat"], timeout=25)
    if result is None:
        return [Check("INFO", "SELinux denials", "journalctl is unavailable; cannot read AVC records")]
    if not result.ok and not result.out:
        return [
            Check(
                "INFO",
                "SELinux denials",
                "no readable AVC records (journal access may need the 'adm' or 'wheel' group)",
            )
        ]
    enforced: dict[tuple[str, str, str, str], int] = {}
    benign = 0
    permissive: dict[str, int] = {}
    for line in result.out.splitlines():
        match = _AVC_RE.search(line)
        if match is None:
            continue
        comm = match["comm"]
        tclass = match["tclass"]
        tcontext = match["tcontext"]
        if match.groupdict().get("permissive") == "1":
            permissive[comm] = permissive.get(comm, 0) + 1
            continue
        if not show_benign and _is_benign(comm, tclass, tcontext):
            benign += 1
            continue
        key = (comm, match["perms"].strip(), tclass, tcontext)
        enforced[key] = enforced.get(key, 0) + 1
    checks: list[Check] = []
    if benign:
        checks.append(
            Check(
                "INFO",
                "SELinux denials",
                f"{benign} known-benign denial(s) hidden (sshd control socket); --show-benign to see them",
            )
        )
    if permissive:
        names = ", ".join(f"{comm} ({count}x)" for comm, count in sorted(permissive.items(), key=lambda i: -i[1])[:4])
        checks.append(
            Check(
                "INFO",
                "SELinux denials",
                f"{sum(permissive.values())} denial(s) in a permissive domain, which blocked nothing: {names}",
            )
        )
    if not enforced:
        checks.append(Check("PASS", "SELinux denials", "no unexplained enforced denials this boot"))
        return checks
    for (comm, perms, tclass, tcontext), count in sorted(
        enforced.items(), key=lambda item: -item[1]
    )[:8]:
        checks.append(
            Check(
                "WARN",
                "SELinux denial",
                f"{comm} denied {{{perms}}} on {tclass} in {tcontext} ({count}x this boot, enforced)",
                "sudo ausearch -m avc -ts boot | audit2allow -w",
            )
        )
    if len(enforced) > 8:
        checks.append(
            Check("INFO", "SELinux denials", f"{len(enforced) - 8} further distinct denial(s) not shown")
        )
    return checks


def _relabel_hint() -> Check | None:
    """A ROM tree mislabelled for SELinux is invisible to a confined Flatpak.

    Everything under a user's home should be `user_home_t`. A separate volume mounted
    there that was formatted elsewhere often comes up `unlabeled_t` or `default_t`
    instead, and the symptom is an emulator that sees an empty folder.
    """
    from .paths import roms_dir

    roms = roms_dir()
    if not roms.is_dir():
        return None
    result = run(["ls", "-Zd", str(roms)])
    if result is None or not result.ok:
        return None
    label = result.text.split()[0] if result.text else ""
    if ":" not in label:
        return None
    kind = label.split(":")[2] if label.count(":") >= 2 else label
    if kind in ("user_home_t", "user_home_dir_t"):
        return Check("PASS", "ROM tree SELinux label", f"{kind} on {roms}")
    return Check(
        "WARN",
        "ROM tree SELinux label",
        f"{kind} on {roms}; a confined process may not be able to read it",
        f"sudo restorecon -RF {roms}",
    )


def _ostree() -> list[Check]:
    checks: list[Check] = []
    if not have("rpm-ostree"):
        return [Check("INFO", "Image", "not an rpm-ostree host; the immutable-root notes do not apply")]
    result = run(["rpm-ostree", "status", "--json"], timeout=30)
    if result is None or not result.ok:
        return [Check("INFO", "Image", "rpm-ostree present but status could not be read")]
    import json

    try:
        deployments = json.loads(result.out).get("deployments", [])
    except (ValueError, AttributeError):
        return [Check("INFO", "Image", "rpm-ostree status was not valid JSON")]
    booted = next((d for d in deployments if d.get("booted")), None)
    if booted is not None:
        version = booted.get("version") or booted.get("checksum", "")[:12]
        # origin is absent on a container-native deployment; say nothing rather than "?".
        origin = booted.get("origin") or booted.get("container-image-reference") or ""
        where = f"{origin} " if origin else ""
        checks.append(Check("PASS", "Image", f"booted {where}version {version}"))
        layered = booted.get("requested-packages") or booted.get("packages") or []
        if layered:
            checks.append(
                Check(
                    "INFO",
                    "Layered packages",
                    f"{len(layered)} layered: {', '.join(sorted(layered)[:8])}",
                )
            )
    staged = next((d for d in deployments if d.get("staged")), None)
    pending = [d for d in deployments if not d.get("booted") and d.get("staged")]
    if staged is not None or pending:
        checks.append(
            Check(
                "WARN",
                "Pending deployment",
                "an update is staged but not booted - the running system is not the one on disk",
                "reboot to apply, or `rpm-ostree cleanup -p` to discard it",
            )
        )
    return checks


def _disks() -> list[Check]:
    """Free space per real filesystem, judged against what the filesystem is for.

    Reports the actual block topology rather than trusting any note about it: on this
    machine the ROM volume is the whole of `nvme0n1` (label RetroDECK) and the OS is
    `nvme1n1p3`, which is the reverse of what the scraper's notes claimed.

    The thresholds are per-filesystem on purpose. A tens-of-GiB rule is right for the
    volume holding ROMs and media and nonsense everywhere else: applied to a 1 GiB EFI
    system partition it reports FAIL on a machine with hundreds of GiB free, which is precisely
    the kind of false alarm that teaches a user to ignore the exit code.
    """
    from .paths import esde_dir, roms_dir

    checks: list[Check] = []
    result = run(["findmnt", "-rno", "SOURCE,TARGET,FSTYPE,LABEL"])
    if result is None:
        return [Check("INFO", "Disks", "findmnt is unavailable")]

    # The mounts that actually carry ROMs, media and gamelists get the strict rule.
    wanted: set[str] = set()
    for path in (roms_dir(), esde_dir(), Path.home()):
        probe = run(["findmnt", "-nro", "TARGET", "-T", str(path)])
        if probe is not None and probe.text:
            wanted.add(probe.text.splitlines()[0].strip())

    # One filesystem is often mounted at several targets - on an ostree host /etc,
    # /var, /var/home and /sysroot are all one btrfs. Report it once, under the target
    # that means something: a mount carrying ROMs or media if there is one, else the
    # shortest path, which is the real mount rather than a deploy-specific bind.
    rows: dict[str, tuple[str, str, str, str]] = {}
    for line in result.out.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        source, target, fstype = parts[0], parts[1], parts[2]
        label = parts[3] if len(parts) > 3 else ""
        if fstype in PSEUDO_FSTYPES or not source.startswith("/dev/"):
            continue
        try:
            usage = shutil.disk_usage(target)
        except OSError:
            continue
        key = f"{usage.total}:{usage.free}"
        existing = rows.get(key)
        if existing is not None:
            better = (target in wanted and existing[1] not in wanted) or (
                existing[1] not in wanted and len(target) < len(existing[1])
            )
            if not better:
                continue
        rows[key] = (source, target, fstype, label)

    for source, target, fstype, label in rows.values():
        try:
            usage = shutil.disk_usage(target)
        except OSError:
            continue
        detail = (
            f"{target} on {source}"
            + (f" (label {label})" if label else "")
            + f" - {human(usage.free)} free of {human(usage.total)}"
        )
        share = usage.free / usage.total if usage.total else 1.0
        if target in wanted:
            if usage.free < MIN_FREE_BYTES:
                checks.append(
                    Check("FAIL", "Disk space", detail, "media and romsets need tens of GiB of headroom")
                )
            elif usage.free < LOW_FREE_BYTES:
                checks.append(Check("WARN", "Disk space", detail))
            else:
                checks.append(Check("PASS", "Disk space", detail))
        elif share < 0.05:
            # Not a RetroDECK filesystem, but nearly full is worth saying whatever it holds.
            checks.append(Check("WARN", "Disk space", detail + f" ({share:.0%} free)"))
        else:
            checks.append(Check("INFO", "Disk space", detail))
    root = shutil.disk_usage("/")
    if root.free == 0:
        checks.append(
            Check(
                "INFO",
                "Root filesystem",
                f"/ is {human(root.total)} and 100% used - normal for an ostree composefs, not a fault",
            )
        )
    return checks


def _kernel() -> Check:
    release = os.uname().release
    flavour = " (Bazzite gaming kernel)" if "bazzite" in release or "ogc" in release else ""
    return Check("INFO", "Kernel", f"{release}{flavour}")


def _brew() -> Check | None:
    """Installed-but-invisible is the interesting case, and it is the usual one."""
    if have("brew"):
        result = run(["brew", "--version"])
        version = result.text.splitlines()[0] if result and result.text else "present"
        return Check("PASS", "Homebrew", f"on PATH - {version}")
    for prefix in (Path("/home/linuxbrew/.linuxbrew"), Path.home() / ".linuxbrew"):
        if (prefix / "bin" / "brew").exists():
            return Check(
                "INFO",
                "Homebrew",
                f"installed at {prefix} but not on PATH in a non-interactive shell",
                f'eval "$({prefix}/bin/brew shellenv)" before calling brew from a script or an agent',
            )
    return Check("INFO", "Homebrew", "not installed")


def _containers() -> list[Check]:
    checks: list[Check] = []
    if not have("distrobox"):
        return [Check("INFO", "distrobox", "not installed")]
    result = run(["distrobox", "list", "--no-color"], timeout=30)
    if result is None or not result.ok:
        return [Check("INFO", "distrobox", "installed but the container list could not be read")]
    rows = [line for line in result.out.splitlines()[1:] if line.strip()]
    if not rows:
        return [Check("INFO", "distrobox", "no containers")]
    for row in rows:
        fields = [field.strip() for field in row.split("|")]
        if len(fields) < 3:
            continue
        name, status = fields[1], fields[2]
        level = "PASS" if status.startswith("Up") else "INFO"
        fix = f"distrobox enter -n {name}  # starts it" if not status.startswith("Up") else ""
        checks.append(Check(level, "distrobox", f"{name}: {status}", fix))
    return checks


def _zram() -> Check | None:
    result = run(["swapon", "--show=NAME,SIZE,USED", "--noheadings", "--bytes"])
    if result is None or not result.text:
        return Check("INFO", "Swap", "no swap configured")
    parts = result.text.split()
    if len(parts) >= 2:
        try:
            return Check("INFO", "Swap", f"{parts[0]} - {human(int(parts[1]))}")
        except ValueError:
            pass
    return Check("INFO", "Swap", result.text.splitlines()[0])


def _audit_log_check(creds) -> Check | None:
    """The audit log proper, which the journal only partly mirrors.

    `/var/log/audit/audit.log` is root-only, so without a password this check says what it
    could not inspect rather than implying the journal was the whole picture. That
    distinction matters: the journal can drop AVC records under pressure, so "no denials
    in the journal" is weaker evidence than "no denials in the audit log".
    """
    from . import env

    if not creds.can_sudo:
        return Check(
            "INFO",
            "Audit log",
            "not inspected - the journal was read instead, which can drop AVC records",
            "sudo ausearch -m avc -ts boot   (or set RDT_SUDO_PASSWORD in .env)",
        )
    result = env.sudo_run(["ausearch", "-m", "avc", "-ts", "boot"], creds, timeout=40)
    if result is None:
        return Check("INFO", "Audit log", "ausearch could not be run under sudo")
    if not result.ok:
        # ausearch exits 1 for "no matches", which is the good outcome, not an error.
        if "no matches" in (result.out + result.err).lower():
            return Check("PASS", "Audit log", "no AVC records at all this boot")
        return Check("INFO", "Audit log", "ausearch reported an error; the journal reading stands")
    denials = result.out.count("avc:  denied")
    permissive = result.out.count("permissive=1")
    if denials == 0:
        return Check("PASS", "Audit log", "no AVC records this boot")
    return Check(
        "INFO",
        "Audit log",
        f"{denials} AVC record(s) this boot, {permissive} of them in a permissive domain",
        "sudo ausearch -m avc -ts boot | audit2allow -w   # explains each in prose",
    )


def collect(*, show_benign: bool = False, creds=None) -> Report:
    report = Report("Host / Bazzite")
    report.add(_kernel())
    report.extend(_ostree())
    report.add(_selinux_mode())
    report.extend(_selinux_denials(show_benign=show_benign))
    if creds is not None:
        report.add(_audit_log_check(creds))
    report.add(_relabel_hint())
    report.extend(_disks())
    report.add(_zram())
    report.add(_brew())
    report.extend(_containers())
    return report
