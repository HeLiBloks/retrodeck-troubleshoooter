"""Flatpak: is the app there, and can it actually reach the ROM tree?

The interesting failure is never "flatpak is broken". It is that an emulator's sandbox
cannot see, or cannot write, the directory holding the games - and the symptom is an
empty system in the carousel or a save that vanishes, neither of which mentions Flatpak.

Three things make that worth computing rather than eyeballing:

- **The ROM tree is usually a separate filesystem mounted under `$HOME`.** On this
  machine `~/retrodeck` is the whole of `nvme0n1` (btrfs, label RetroDECK) mounted inside
  a home that lives on `nvme1n1p3`. A `filesystems=home` grant does carry submounts
  along, but a grant of some *specific* `~/subdir` does not help a sibling.
- **`:ro` is a real difference and reads as a bug elsewhere.** Ryujinx here holds
  `filesystems=home:ro`, so it can load a ROM from `~/retrodeck` and cannot write a save
  beside it. Its own `~/.var/app` data directory is always writable, which is why most
  things work and only some fail.
- **Overrides are invisible in the manifest.** Flatseal writes to
  `~/.local/share/flatpak/overrides/<app>` and `/var/lib/flatpak/overrides/<app>`, and
  `flatpak info --show-permissions` already folds them in - but knowing *which* grant
  came from an override is what tells you whether a permission is the app's design or
  something that was changed by hand and can be changed back.
"""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from .probe import Check, Report, have, home, run

# Grants that mean "everything", in decreasing breadth.
_WHOLE_HOST = ("host", "host-os", "host-etc")

_XDG_DEFAULTS = {
    "xdg-config": ".config",
    "xdg-cache": ".cache",
    "xdg-data": ".local/share",
    "xdg-documents": "Documents",
    "xdg-download": "Downloads",
    "xdg-pictures": "Pictures",
    "xdg-music": "Music",
    "xdg-videos": "Videos",
    "xdg-desktop": "Desktop",
    "xdg-public-share": "Public",
    "xdg-templates": "Templates",
}


@dataclass(frozen=True, slots=True)
class Grant:
    """One `filesystems=` entry, split into the path it covers and the mode."""

    raw: str
    path: Path | None
    mode: str  # "rw", "ro", "create", or "all" for a whole-host grant

    @property
    def writable(self) -> bool:
        return self.mode in ("rw", "create", "all")


def parse_grant(entry: str) -> Grant:
    text = entry.strip()
    if not text:
        return Grant(entry, None, "rw")
    mode = "rw"
    for suffix in (":ro", ":rw", ":create"):
        if text.endswith(suffix):
            mode = suffix[1:]
            text = text[: -len(suffix)]
            break
    if text in _WHOLE_HOST:
        return Grant(entry, Path("/"), "all" if mode == "rw" else mode)
    if text == "home":
        return Grant(entry, home(), mode)
    head, _, tail = text.partition("/")
    if head in _XDG_DEFAULTS:
        base = home() / _XDG_DEFAULTS[head]
        return Grant(entry, base / tail if tail else base, mode)
    if head.startswith("xdg-run"):
        base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
        return Grant(entry, base / tail if tail else base, mode)
    if text.startswith("~/"):
        return Grant(entry, home() / text[2:], mode)
    if text.startswith("/"):
        return Grant(entry, Path(text), mode)
    return Grant(entry, None, mode)


def _covers(grant: Grant, target: Path) -> bool:
    if grant.path is None:
        return False
    try:
        target.relative_to(grant.path)
        return True
    except ValueError:
        pass
    # A grant spelled the other way round the /home -> /var/home symlink still covers it.
    from .paths import spelling_variants

    for variant in spelling_variants(target):
        try:
            variant.relative_to(grant.path)
            return True
        except ValueError:
            continue
    return False


def access_to(grants: list[Grant], target: Path) -> Grant | None:
    """The broadest grant covering `target`, preferring a writable one."""
    matching = [grant for grant in grants if _covers(grant, target)]
    if not matching:
        return None
    matching.sort(key=lambda g: (g.writable, len(str(g.path or ""))), reverse=True)
    return matching[0]


def permissions(app_id: str) -> dict[str, dict[str, str]] | None:
    """`flatpak info --show-permissions`, parsed. None when the app is not installed."""
    result = run(["flatpak", "info", "--show-permissions", app_id], timeout=25)
    if result is None or not result.ok or not result.out.strip():
        return None
    parser = configparser.RawConfigParser()
    parser.optionxform = str  # keys here are case-sensitive
    try:
        parser.read_string(result.out)
    except configparser.Error:
        return None
    return {section: dict(parser.items(section)) for section in parser.sections()}


def grants_for(app_id: str) -> list[Grant]:
    perms = permissions(app_id) or {}
    raw = perms.get("Context", {}).get("filesystems", "")
    return [parse_grant(entry) for entry in raw.split(";") if entry.strip()]


def override_files(app_id: str) -> list[Path]:
    candidates = [
        home() / ".local/share/flatpak/overrides" / app_id,
        Path("/var/lib/flatpak/overrides") / app_id,
        home() / ".local/share/flatpak/overrides/global",
        Path("/var/lib/flatpak/overrides/global"),
    ]
    return [path for path in candidates if path.is_file()]


def installation_of(app_id: str) -> tuple[str, str] | None:
    """(scope, version) for wherever the app is installed, or None."""
    for scope in ("--system", "--user"):
        result = run(["flatpak", "info", scope, app_id], timeout=25)
        if result is None or not result.ok:
            continue
        version = "unknown"
        for line in result.out.splitlines():
            if line.strip().startswith("Version:"):
                version = line.split(":", 1)[1].strip() or version
                break
        return scope.lstrip("-"), version
    return None


def _install_check(app_id: str, label: str, *, required: bool) -> Check:
    found = installation_of(app_id)
    if found is None:
        level = "FAIL" if required else "INFO"
        return Check(level, f"{label} install", "not installed in either scope")
    scope, version = found
    return Check("PASS", f"{label} install", f"{scope} scope, version {version}")


def _reach_check(app_id: str, label: str, target: Path, *, need_write: bool) -> Check:
    grants = grants_for(app_id)
    if not grants:
        return Check("INFO", f"{label} sandbox", "no filesystem grants could be read")
    grant = access_to(grants, target)
    if grant is None:
        return Check(
            "FAIL",
            f"{label} sandbox",
            f"no grant covers {target} - the sandbox cannot see it at all",
            f"flatpak override --user --filesystem={target} {app_id}",
        )
    if need_write and not grant.writable:
        return Check(
            "WARN",
            f"{label} sandbox",
            f"{target} is reachable read-only via '{grant.raw}'; writes beside the ROM will fail",
            f"flatpak override --user --filesystem={target} {app_id}   # adds rw",
        )
    breadth = "whole host" if grant.mode == "all" else grant.raw
    return Check("PASS", f"{label} sandbox", f"{target} reachable ({breadth})")


def _overrides_check(app_id: str, label: str) -> Check | None:
    files = override_files(app_id)
    if not files:
        return None
    parts: list[str] = []
    for path in files:
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        keys = sorted({line.split("=", 1)[0].strip() for line in text.splitlines() if "=" in line})
        scope = "user" if str(home()) in str(path) else "system"
        name = "global" if path.name == "global" else "app"
        parts.append(f"{scope}/{name}: {', '.join(keys[:6]) or 'empty'}")
    if not parts:
        return None
    return Check(
        "INFO",
        f"{label} overrides",
        "; ".join(parts),
        f"flatpak override --user --show {app_id}  # and --reset to undo hand edits",
    )


def _sandbox_probe(app_id: str, label: str, target: Path) -> Check:
    """Ground truth: ask the sandbox itself whether it can read the directory.

    Static analysis of `filesystems=` gets the answer right for every case measured
    here, but it is a model of Flatpak's behaviour rather than Flatpak's behaviour -
    and the submount question in particular is one where the model could be wrong. This
    runs `sh` inside the app's own runtime, which starts no emulator and writes nothing.
    """
    result = run(
        [
            "flatpak",
            "run",
            "--command=sh",
            app_id,
            "-c",
            f'if [ -r "{target}" ]; then ls -1 "{target}" | head -3; else echo UNREADABLE; fi',
        ],
        timeout=90,
    )
    if result is None:
        return Check("INFO", f"{label} sandbox probe", "could not launch the runtime")
    output = result.out.strip()
    if "UNREADABLE" in output or (not result.ok and not output):
        return Check(
            "FAIL",
            f"{label} sandbox probe",
            f"the sandbox cannot read {target} (stderr: {result.err.strip()[:120]})",
            f"flatpak override --user --filesystem={target} {app_id}",
        )
    if not output:
        return Check("WARN", f"{label} sandbox probe", f"{target} is readable but appears empty inside the sandbox")
    first = ", ".join(output.splitlines()[:3])
    return Check("PASS", f"{label} sandbox probe", f"read {target} inside the sandbox: {first}")


def _eol_runtimes() -> Check | None:
    result = run(["flatpak", "list", "--runtime", "--columns=application,branch,options"], timeout=30)
    if result is None or not result.ok:
        return None
    eol = [line for line in result.out.splitlines() if "eol" in line.lower()]
    if not eol:
        return None
    names = ", ".join(line.split()[0] for line in eol[:5])
    return Check(
        "WARN",
        "Flatpak runtimes",
        f"{len(eol)} end-of-life runtime(s) installed: {names}",
        "flatpak uninstall --unused",
    )


def _system_overrides_check(app_id: str, label: str, creds) -> Check | None:
    """System-scope overrides, which live where an ordinary user often cannot read.

    Worth a privileged look because a system override is exactly the kind of change that
    is made once, forgotten, and then blamed on the app's own manifest.
    """
    from . import env

    path = Path("/var/lib/flatpak/overrides") / app_id
    if os.access(path, os.R_OK):
        return None  # the unprivileged path already reported it
    if not creds.can_sudo:
        return None
    result = env.sudo_run(["cat", str(path)], creds)
    if result is None or not result.ok:
        return None
    keys = sorted({line.split("=", 1)[0].strip() for line in result.out.splitlines() if "=" in line})
    if not keys:
        return None
    return Check(
        "INFO",
        f"{label} system override",
        f"/var/lib/flatpak/overrides/{app_id} sets: {', '.join(keys[:6])}",
        f"sudo flatpak override --show {app_id}",
    )


def collect(*, probe: bool = False, creds=None) -> Report:
    from .paths import RETRODECK_APP_ID, RYUJINX_APP_ID, SUPERMODEL_APP_ID, roms_dir

    report = Report("Flatpak")
    if not have("flatpak"):
        report.add(Check("FAIL", "Flatpak", "the flatpak command is unavailable"))
        return report
    version = run(["flatpak", "--version"])
    report.add(Check("PASS", "Flatpak", version.text if version and version.text else "present"))

    roms = roms_dir()
    apps = (
        (RETRODECK_APP_ID, "RetroDECK", True, True),
        (RYUJINX_APP_ID, "Ryujinx", False, True),
        (SUPERMODEL_APP_ID, "Supermodel", False, False),
    )
    for app_id, label, required, need_write in apps:
        report.add(_install_check(app_id, label, required=required))
        if installation_of(app_id) is None:
            continue
        if roms.exists():
            report.add(_reach_check(app_id, label, roms, need_write=need_write))
            if probe:
                report.add(_sandbox_probe(app_id, label, roms))
        report.add(_overrides_check(app_id, label))
        if creds is not None:
            report.add(_system_overrides_check(app_id, label, creds))
    report.add(_eol_runtimes())
    return report
