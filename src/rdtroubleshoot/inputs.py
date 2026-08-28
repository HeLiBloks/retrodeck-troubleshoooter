"""Controllers, and the single most misleading emulator symptom there is.

**A black screen after the game loads is almost always an unbound pad, not a GPU fault.**
Ryujinx logs, every two seconds, for the whole session:

    |W| Hid Remap: No matching controllers found.
        Application requests 'ProController, Handheld, JoyconPair'
        on 'Player1, Player2, Player3, Player4, Handheld'

The game is running and waiting for input that never arrives. Audio comes up and a
handful of shaders compile, so everything looks alive. Measured on this machine: a
DualShock 4 *was* connected and Ryujinx *saw* it - it simply had no profile whose id
matched, because the only binding in `Config.json` was for an X360 pad.

That id is derivable rather than guessable, which is what `controller_guid()` is for.
Ryujinx stores a .NET `Guid` laid over SDL's 16-byte joystick GUID, and every field of it
comes from the kernel's own `id/` directory in sysfs. Deriving it beats guessing, and
beats plugging in a pad to read it back out of the GUI.

One caveat that matters when you run this over SSH: udev grants the *locally seated*
user access to input devices through a POSIX ACL (the `uaccess` tag). An SSH session is
not on that seat, so this module can correctly report "no ACL for you" while the desktop
session has one. It says so rather than calling it a fault.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .probe import Check, Report, have, run

SYS_INPUT = Path("/sys/class/input")
# The kernel modules that make a pad usable, and the ones that name a pad's family.
PAD_MODULES = ("joydev", "uinput", "hid_sony", "hid_playstation", "xpad", "hid_nintendo", "hid_steam")


@dataclass(frozen=True, slots=True)
class Pad:
    name: str
    bustype: int
    vendor: int
    product: int
    version: int
    sysfs: Path
    js_nodes: tuple[str, ...]
    event_nodes: tuple[str, ...]

    @property
    def ids(self) -> str:
        return f"{self.vendor:04x}:{self.product:04x}"


def _sdl_guid_bytes(bustype: int, vendor: int, product: int, version: int) -> bytes:
    """SDL2's 16-byte evdev joystick GUID.

    Layout is four little-endian 16-bit values, each followed by two zero bytes:
    bustype, vendor, product, version. The zero slots are SDL's CRC and driver fields,
    which are zero for a plain evdev pad.
    """
    return b"".join(
        value.to_bytes(2, "little") + b"\x00\x00"
        for value in (bustype, vendor, product, version)
    )


def controller_guid(bustype: int, vendor: int, product: int, version: int, *, player_index: int = 0) -> str:
    """The id Ryujinx writes in `Config.json`, e.g. `0-00000003-054c-0000-c405-000011810000`.

    Ryujinx builds a .NET `Guid` from the SDL bytes, and .NET's `Guid(byte[])` reads the
    first three fields little-endian and the last eight bytes raw - which is why the
    vendor appears byte-swapped in the second group but not in the fourth.
    """
    raw = _sdl_guid_bytes(bustype, vendor, product, version)
    field1 = int.from_bytes(raw[0:4], "little")
    field2 = int.from_bytes(raw[4:6], "little")
    field3 = int.from_bytes(raw[6:8], "little")
    tail = raw[8:16].hex()
    return f"{player_index}-{field1:08x}-{field2:04x}-{field3:04x}-{tail[:4]}-{tail[4:]}"


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text().strip(), 16)
    except (OSError, ValueError):
        return None


def discover_pads() -> list[Pad]:
    """Every input device the kernel has bound a joystick node to.

    Keying on the presence of a `js*` child is deliberate: it means joydev claimed the
    device, i.e. the kernel agrees it is a joystick. A keyboard or a laptop lid switch
    has an `event*` node and never a `js*` one.
    """
    pads: list[Pad] = []
    if not SYS_INPUT.is_dir():
        return pads
    for entry in sorted(SYS_INPUT.glob("input*")):
        ident = entry / "id"
        if not ident.is_dir():
            continue
        js = tuple(sorted(child.name for child in entry.iterdir() if re.fullmatch(r"js\d+", child.name)))
        events = tuple(sorted(child.name for child in entry.iterdir() if re.fullmatch(r"event\d+", child.name)))
        if not js:
            continue
        values = {key: _read_int(ident / key) for key in ("bustype", "vendor", "product", "version")}
        if any(value is None for value in values.values()):
            continue
        try:
            name = (entry / "name").read_text().strip()
        except OSError:
            name = "unknown"
        pads.append(
            Pad(
                name=name,
                bustype=values["bustype"] or 0,
                vendor=values["vendor"] or 0,
                product=values["product"] or 0,
                version=values["version"] or 0,
                sysfs=entry,
                js_nodes=js,
                event_nodes=events,
            )
        )
    return pads


def _modules() -> Check:
    try:
        loaded = {line.split()[0] for line in Path("/proc/modules").read_text().splitlines() if line.split()}
    except OSError:
        return Check("INFO", "Input modules", "/proc/modules is unreadable")
    present = [name for name in PAD_MODULES if name in loaded]
    if "joydev" not in present:
        return Check(
            "WARN",
            "Input modules",
            "joydev is not loaded, so no /dev/input/js* nodes will appear",
            "sudo modprobe joydev",
        )
    return Check("PASS", "Input modules", f"loaded: {', '.join(present)}")


def _readability(pads: list[Pad]) -> list[Check]:
    """Can this user actually open the device nodes?

    Reported as INFO rather than WARN when it fails over SSH, because udev's `uaccess`
    ACL is granted to the seated user and an SSH session is not seated. The desktop
    session may well have access that this check cannot see.
    """
    if not pads:
        return []
    import os

    unreadable: list[str] = []
    for pad in pads:
        for node in pad.js_nodes + pad.event_nodes:
            device = Path("/dev/input") / node
            if device.exists() and not os.access(device, os.R_OK):
                unreadable.append(node)
    if not unreadable:
        return [Check("PASS", "Input device access", "every pad node is readable by this user")]
    in_group = False
    groups = run(["id", "-nG"])
    if groups is not None:
        in_group = "input" in groups.text.split()
    seated = bool(run(["loginctl", "show-user", str(os.getuid()), "-p", "Display"]))
    detail = f"{len(unreadable)} node(s) not readable by this user: {', '.join(unreadable[:4])}"
    if in_group:
        return [Check("WARN", "Input device access", detail + " despite membership of the 'input' group")]
    return [
        Check(
            "INFO",
            "Input device access",
            detail
            + " - normal over SSH, since udev grants access to the locally seated user by ACL",
            "check from the desktop session before changing anything; "
            "`sudo usermod -aG input $USER` is the blunt fix and is rarely needed",
        )
    ]


def ryujinx_bindings() -> list[dict] | None:
    """The `input_config` array from Ryujinx's Config.json, or None."""
    config = paths.ryujinx_config()
    if not config.is_file():
        return None
    try:
        data = json.loads(config.read_text(errors="replace"))
    except (OSError, ValueError):
        return None
    bindings = data.get("input_config")
    return bindings if isinstance(bindings, list) else None


def _ryujinx_check(pads: list[Pad]) -> list[Check]:
    config = paths.ryujinx_config()
    if not config.is_file():
        return [Check("INFO", "Ryujinx input", f"no Config.json at {config}")]
    bindings = ryujinx_bindings()
    if bindings is None:
        return [Check("WARN", "Ryujinx input", "Config.json could not be parsed for input_config")]
    try:
        data = json.loads(config.read_text(errors="replace"))
    except (OSError, ValueError):
        data = {}
    checks: list[Check] = []
    bound_ids = {str(entry.get("id", "")).lower() for entry in bindings}
    keyboard = any(entry.get("backend") == "WindowKeyboard" for entry in bindings)
    enable_keyboard = bool(data.get("enable_keyboard", False))
    docked = bool(data.get("docked_mode", True))
    if not bindings:
        checks.append(
            Check(
                "FAIL",
                "Ryujinx input",
                "no input profile at all - every game will load to a black screen",
                "Options -> Settings -> Input -> Player 1, and bind the pad that is connected",
            )
        )
    else:
        summary = ", ".join(
            f"{entry.get('player_index', '?')}={entry.get('name') or entry.get('backend', '?')}"
            for entry in bindings[:4]
        )
        checks.append(Check("INFO", "Ryujinx profiles", f"{len(bindings)} binding(s): {summary}"))
    if not pads:
        checks.append(
            Check(
                "INFO",
                "Ryujinx input match",
                "no joystick is currently connected, so the bindings cannot be checked against one",
            )
        )
        return checks
    unmatched: list[Pad] = []
    for pad in pads:
        expected = controller_guid(pad.bustype, pad.vendor, pad.product, pad.version)
        # The player index is the leading field and varies; compare everything after it.
        tail = expected.split("-", 1)[1]
        if not any(tail in bound for bound in bound_ids):
            unmatched.append(pad)
    if not unmatched:
        checks.append(Check("PASS", "Ryujinx input match", "every connected pad has a matching profile"))
        return checks

    # **Severity depends on whether anything else can drive the game.** With a keyboard
    # profile bound and docked mode off, an unmatched pad means "this pad will not work" -
    # annoying, but the game starts and responds. With no fallback at all, nothing is bound
    # and the game loads to a black screen and waits for ever. Calling both FAIL overstates
    # the first and, worse, cites the black-screen symptom for a case that will not show it.
    has_fallback = keyboard or enable_keyboard or not docked
    for pad in unmatched:
        expected = controller_guid(pad.bustype, pad.vendor, pad.product, pad.version)
        fix = (
            f"bind it in the GUI, or add a profile with id {expected} "
            f"(close Ryujinx first - it rewrites Config.json on exit)"
        )
        if has_fallback:
            how = []
            if keyboard or enable_keyboard:
                how.append("a keyboard binding")
            if not docked:
                how.append("the Handheld slot")
            checks.append(
                Check(
                    "WARN",
                    "Ryujinx input match",
                    f"'{pad.name}' ({pad.ids}) is connected but no profile matches it, so that pad "
                    f"will not work - the game will still start, because {' and '.join(how)} "
                    f"remain available",
                    fix,
                )
            )
        else:
            checks.append(
                Check(
                    "FAIL",
                    "Ryujinx input match",
                    f"'{pad.name}' ({pad.ids}) is connected, no profile matches it, and there is "
                    f"no keyboard or Handheld fallback - the game will load to a black screen and "
                    f"wait for input for ever",
                    fix,
                )
            )
    if not keyboard and not enable_keyboard:
        checks.append(
            Check(
                "WARN",
                "Ryujinx fallback",
                "enable_keyboard is false and no keyboard profile exists, so there is no fallback"
                + (" and docked_mode removes the Handheld option too" if docked else ""),
            )
        )
    return checks


def collect() -> Report:
    report = Report("Controllers / input")
    report.add(_modules())
    pads = discover_pads()
    if pads:
        for pad in pads:
            report.add(
                Check(
                    "INFO",
                    "Pad detected",
                    f"'{pad.name}' {pad.ids} on {', '.join(pad.js_nodes)} - "
                    f"Ryujinx id {controller_guid(pad.bustype, pad.vendor, pad.product, pad.version)}",
                )
            )
    else:
        report.add(
            Check(
                "INFO",
                "Pad detected",
                "none - no /dev/input/js* node is bound to any device",
                "a game that loads to a black screen with no pad connected is waiting for input",
            )
        )
    report.extend(_readability(pads))
    report.extend(_ryujinx_check(pads))
    return report
