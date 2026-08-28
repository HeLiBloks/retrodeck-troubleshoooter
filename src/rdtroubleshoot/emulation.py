"""RetroDECK and its emulators: layout, gamelists, logs, and the two known runtime traps.

Everything here was derived by reading the logs on the test machine rather than from the
documentation, and each check stands for something that cost a session:

- `mesa_glthread` is logged at `|E|` severity by Ryujinx and is **noise** - a Mesa
  message, on a machine where Mesa is not driving the game. Unfiltered it drowns every
  real error in the file.
- A **black screen after loading** is `Hid Remap: No matching controllers found`, not a
  GPU fault. See `inputs.py`.
- A Switch **update NSP** (`...800`) contains no application and can never launch. That is
  correct behaviour, not a broken dump.
- **Supermodel needs `WAYLAND_DISPLAY=`** unset and its own working directory, or it dies
  with "OpenGL initialization failed: Unknown error".
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from . import gamelist as gl
from . import paths
from .probe import Check, Report, home, human, run, tail_lines

# Ryujinx logs this at error severity and it is not an error.
LOG_NOISE_RE = re.compile(r"mesa_glthread|ATTENTION: default value of option", re.IGNORECASE)
# **Two log formats are interleaved in one file** and the scan must read both. The
# emulators use Ryujinx's `|E|` / `|W|`; ES-DE and RetroDECK itself use `[ERROR]` /
# `[WARN]`. Reading only the first reported "no real |E| lines" on a log holding 124
# `[WARN]` and one `[ERROR]` - a false clean, which is the worst thing a checker can say.
ERROR_LINE_RE = re.compile(r"\|E\||\[ERROR\]")
WARN_LINE_RE = re.compile(r"\|W\||\[WARN\]")
# A gamelist entry whose extension the system does not declare is a game ES-DE lists and
# cannot open. It logs twice per entry, so the two lines are counted as one finding.
DEAD_ENTRY_RE = re.compile(
    r"extension is not configured in es_systems\.xml|Couldn't process \"", re.IGNORECASE
)
MISSING_FILE_RE = re.compile(r"(File|Folder) \"([^\"]+)\" does not exist, skipping entry")
# Below this, a repeating warning class is chatter rather than a pattern.
WARN_CLASS_FLOOR = 3
# Error-severity lines that are known, understood, and harmless. Reported as INFO with the
# explanation rather than dropped, which is how this project treats the benign SELinux
# denials too: counted and named, never hidden. Suppressing an error silently is how a
# checker goes blind, and warning about a known-normal one is how its exit code stops
# being read - so neither.
BENIGN_ERRORS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"setReportingLevelFromRetroDeckConfig.*RETRODECK_CONFIG_HOME", re.IGNORECASE),
        "RetroDECK startup quirk: the variable is unset when ES-DE reads it, so logging "
        "falls back to DEBUG. Consequence is a verbose log and nothing else",
    ),
)
LAUNCH_RE = re.compile(r"Launching game .*? from system '?([\w-]+)'?", re.IGNORECASE)
# One pattern for "is RetroDECK running", so the checker and any writer cannot drift.
RETRODECK_PROCESS_TERMS = ("es-de", "emulationstation", "net.retrodeck")
# A Switch title id ending 800 is an update, not a game.
UPDATE_NSP_RE = re.compile(r"\[0[0-9A-F]{12}800\]", re.IGNORECASE)
DETAIL_TAGS = ("desc", "genre", "publisher", "developer", "players", "releasedate", "rating")


def _bracketed_pattern() -> str:
    """`[e]s-de|...` - the brackets stop pgrep matching its own command line.

    A plain `pgrep -af 'es-de|...'` reports RetroDECK running when it is not, because the
    pattern is in pgrep's own argv. This bit us over SSH.
    """
    return "|".join(f"[{term[0]}]{term[1:]}" for term in RETRODECK_PROCESS_TERMS)


def _running() -> Check:
    result = run(["pgrep", "-a", "-f", _bracketed_pattern()])
    if result is None:
        return Check("INFO", "RetroDECK process", "could not query processes")
    if result.code == 0:
        first = result.out.splitlines()[0] if result.out.strip() else "process found"
        # A state, not a fault: it does mean every gamelist writer will refuse.
        return Check(
            "INFO",
            "RetroDECK process",
            f"running, so any gamelist write will refuse: {first[:100]}",
            "close RetroDECK before scraping - ES-DE rewrites every gamelist on exit",
        )
    if result.code == 1:
        return Check("PASS", "RetroDECK process", "not running; gamelists are safe to write")
    return Check("INFO", "RetroDECK process", f"pgrep exited {result.code}")


def _layout() -> list[Check]:
    checks: list[Check] = []
    root = paths.retrodeck_root()
    if not root.is_dir():
        return [
            Check(
                "FAIL",
                "RetroDECK layout",
                f"{root} does not exist",
                "set RETRODECK_HOME, or run RetroDECK once so it builds its tree",
            )
        ]
    checks.append(Check("PASS", "RetroDECK layout", f"root {root}"))
    for label, path in (
        ("ROMs", paths.roms_dir()),
        ("gamelists", paths.gamelists_dir()),
        ("downloaded media", paths.media_dir()),
        ("BIOS", paths.bios_dir()),
    ):
        if path.is_dir():
            checks.append(Check("PASS", f"{label} directory", str(path)))
        else:
            checks.append(
                Check(
                    "WARN" if label == "BIOS" else "FAIL",
                    f"{label} directory",
                    f"missing: {path}",
                    "RetroDECK <= 0.8 used a different layout, which is not supported",
                )
            )
    # The ROM tree is very often its own volume; say so, since it changes what a df means.
    roms = paths.roms_dir()
    if roms.is_dir():
        mount = run(["findmnt", "-nro", "SOURCE,FSTYPE,LABEL,OPTIONS", "-T", str(roms)])
        if mount is not None and mount.text:
            fields = mount.text.split()
            source = fields[0] if fields else "?"
            fstype = fields[1] if len(fields) > 1 else "?"
            label = fields[2] if len(fields) > 2 else ""
            opts = fields[3] if len(fields) > 3 else ""
            ro = "ro," in opts or opts.startswith("ro")
            detail = f"{source} ({fstype}{', label ' + label if label else ''})"
            if ro:
                checks.append(
                    Check("FAIL", "ROM volume", f"{detail} is mounted READ-ONLY", "remount rw before writing")
                )
            else:
                checks.append(Check("INFO", "ROM volume", detail))
    return checks


def _path_prefix_trap() -> list[Check]:
    """The `/home` vs `/var/home` spelling mismatch, per gamelist.

    Both spellings reach the same directory, and ES-DE/Skyscraper match entries by the
    raw `<path>` string, so a file holding both spellings loses metadata on the next
    generate. This is the single most expensive bug in the parent project.
    """
    checks: list[Check] = []
    roms = paths.roms_dir()
    variants = paths.spelling_variants(roms)
    if not variants:
        return []
    other = variants[0]
    checks.append(
        Check(
            "INFO",
            "Path spellings",
            f"{roms} is also spelled {other}; the two are NOT interchangeable in a gamelist",
        )
    )
    listing = paths.gamelists_dir()
    if not listing.is_dir():
        return checks
    for path in sorted(listing.glob("*/gamelist.xml")):
        entries = gl.paths_in(path)
        absolute = [entry for entry in entries if entry.startswith("/")]
        if not absolute:
            continue
        spellings = {"/var/home" if entry.startswith("/var/home") else "/home" for entry in absolute if entry.startswith(("/home/", "/var/home/"))}
        if len(spellings) > 1:
            checks.append(
                Check(
                    "FAIL",
                    f"Gamelist spelling ({path.parent.name})",
                    f"mixes {' and '.join(sorted(spellings))} in {len(absolute)} absolute path(s)",
                    "regenerating this system will drop the entries under the minority spelling",
                )
            )
    if not any(check.level == "FAIL" for check in checks):
        checks.append(Check("PASS", "Gamelist spellings", "no gamelist mixes the two home spellings"))
    return checks


def _gamelists() -> list[Check]:
    checks: list[Check] = []
    listing = paths.gamelists_dir()
    if not listing.is_dir():
        return []
    files = sorted(listing.glob("*/gamelist.xml"))
    if not files:
        return [Check("INFO", "Gamelists", f"none under {listing}")]
    broken: list[str] = []
    sibling: list[str] = []
    total_games = 0
    for path in files:
        try:
            parsed = gl.read(path)
        except ET.ParseError as error:
            broken.append(f"{path.parent.name}: {error}")
            continue
        except OSError as error:
            broken.append(f"{path.parent.name}: {error}")
            continue
        total_games += len(parsed.games)
        if parsed.siblings:
            sibling.append(path.parent.name)
    checks.append(
        Check("PASS", "Gamelists", f"{len(files)} file(s), {total_games} game entries, all parsed")
        if not broken
        else Check("FAIL", "Gamelists", f"{len(broken)} unparseable: {'; '.join(broken[:3])}")
    )
    if sibling:
        checks.append(
            Check(
                "INFO",
                "Alternative emulator",
                f"{len(sibling)} gamelist(s) carry ES-DE's sibling <alternativeEmulator> root: {', '.join(sibling[:6])}",
                "ES-DE accepts this; a plain XML parser will not, so tools must handle it",
            )
        )
    return checks


def coverage() -> list[tuple[str, int, dict[str, int]]]:
    """(system, entries, per-tag counts) for every gamelist, worst-covered first."""
    rows: list[tuple[str, int, dict[str, int]]] = []
    listing = paths.gamelists_dir()
    if not listing.is_dir():
        return rows
    for path in sorted(listing.glob("*/gamelist.xml")):
        try:
            parsed = gl.read(path)
        except (ET.ParseError, OSError):
            continue
        games = parsed.games
        if not games:
            continue
        rows.append((path.parent.name, len(games), gl.tag_counts(parsed, DETAIL_TAGS)))
    rows.sort(key=lambda row: (row[2]["desc"] / row[1]) if row[1] else 1.0)
    return rows


def _normalise(line: str) -> str:
    """Collapse timestamps and quoted paths so repeats of one class group together."""
    text = re.sub(r"^\[[0-9 :.\-]+\]\s*", "", line.strip())
    text = re.sub(r"\d{2}:\d{2}:\d{2}[.,]\d+", "<t>", text)
    return re.sub(r'"[^"]*"', '"X"', text)


def _log_scan() -> list[Check]:
    """Errors and repeating warnings from the tail, in both of the file's formats.

    A repeating `|W|` is often more informative than a one-off `|E|` - the
    black-screen-after-loading case is exactly that shape - so warnings are grouped and
    reported rather than dropped. They are INFO unless the class has a known meaning,
    because ES-DE emits ordinary chatter here too and a checker that warns on all of it
    teaches its user to ignore the exit code.
    """
    checks: list[Check] = []
    log = paths.retrodeck_log()
    if not log.is_file():
        return [Check("INFO", "RetroDECK log", f"not present at {log}")]
    try:
        size = log.stat().st_size
    except OSError:
        size = 0
    lines = tail_lines(log, limit=12000)
    checks.append(Check("INFO", "RetroDECK log", f"{log} ({human(size)}, last {len(lines)} lines scanned)"))
    launches = [match.group(1) for line in lines for match in [LAUNCH_RE.search(line)] if match]
    if launches:
        checks.append(Check("INFO", "Recent launches", f"last: {', '.join(reversed(launches[-5:]))}"))

    noise = sum(1 for line in lines if ERROR_LINE_RE.search(line) and LOG_NOISE_RE.search(line))
    if noise:
        checks.append(
            Check("INFO", "Log noise filtered", f"{noise} mesa_glthread line(s) at error severity ignored")
        )

    errors: dict[str, int] = {}
    warnings: dict[str, int] = {}
    benign: dict[str, int] = {}
    for line in lines:
        if LOG_NOISE_RE.search(line):
            continue
        matched_benign = next(
            (why for pattern, why in BENIGN_ERRORS if pattern.search(line)), None
        )
        if matched_benign is not None:
            benign[matched_benign] = benign.get(matched_benign, 0) + 1
            continue
        if ERROR_LINE_RE.search(line):
            key = _normalise(line)[:180]
            errors[key] = errors.get(key, 0) + 1
        elif WARN_LINE_RE.search(line):
            key = _normalise(line)[:180]
            warnings[key] = warnings.get(key, 0) + 1

    for why, count in sorted(benign.items(), key=lambda item: -item[1]):
        checks.append(Check("INFO", "Known-benign log error", f"{why} ({count}x)"))

    if errors:
        for key, count in sorted(errors.items(), key=lambda item: -item[1])[:6]:
            checks.append(Check("WARN", "Log error", f"{key} ({count}x)"))
        if len(errors) > 6:
            checks.append(
                Check("INFO", "Log errors", f"{len(errors) - 6} further distinct error(s) not shown")
            )
    else:
        checks.append(Check("PASS", "Log errors", "no error-severity lines in the scanned tail"))

    # One class has a concrete meaning and a concrete fix, so it gets its own finding
    # rather than being folded into the grouped chatter.
    dead = [line for line in lines if DEAD_ENTRY_RE.search(line)]
    if dead:
        paths_named = {
            match.group(0) for line in dead for match in [re.search(r'"([^"]+)"', line)] if match
        }
        systems = sorted({
            match.group(1)
            for line in dead
            for match in [re.search(r"/roms/([^/]+)/", line)]
            if match
        })
        checks.append(
            Check(
                "WARN",
                "Dead gamelist entries",
                f"{len(paths_named)} entr{'y' if len(paths_named) == 1 else 'ies'} are in a gamelist "
                f"with an extension the system does not declare, so ES-DE lists them and cannot "
                f"open them — system(s): {', '.join(systems) or 'unknown'}",
                "remove those entries from the gamelist, or add the extension to the system's "
                "es_systems.xml — check which is right before doing either",
            )
        )

    missing = [
        match.group(2)
        for line in lines
        for match in [MISSING_FILE_RE.search(line)]
        if match
    ]
    if missing:
        checks.append(
            Check(
                "INFO",
                "Stale gamelist entries",
                f"{len(set(missing))} path(s) in a gamelist no longer exist, e.g. "
                f"{sorted(set(missing))[0]}",
                "harmless — ES-DE skips them; they clear on the next gamelist write",
            )
        )

    other = {
        key: count
        for key, count in warnings.items()
        if not DEAD_ENTRY_RE.search(key) and not MISSING_FILE_RE.search(key)
    }
    if other:
        top = sorted(other.items(), key=lambda item: -item[1])[:4]
        detail = "; ".join(f"{key[:90]} ({count}x)" for key, count in top)
        checks.append(Check("INFO", "Log warnings", f"{sum(other.values())} line(s) — {detail}"))
    return checks


def _bios_log() -> Check | None:
    log = paths.bios_log()
    if not log.is_file():
        return Check("INFO", "BIOS check log", "not present; run RetroDECK's own BIOS check to create it")
    lines = tail_lines(log, limit=2000)
    missing = [line.strip() for line in lines if re.search(r"\bmissing\b", line, re.IGNORECASE)]
    if not missing:
        return Check("PASS", "BIOS check log", "no 'missing' lines in the tail")
    return Check(
        "WARN",
        "BIOS check log",
        f"{len(missing)} line(s) report a missing BIOS, e.g. {missing[-1][:110]}",
        "a missing BIOS stops the core loading, and looks like a broken ROM",
    )


def _switch_updates() -> list[Check]:
    """Update NSPs are not games. Flag them, and never suggest deleting them."""
    switch = paths.roms_dir() / "switch"
    if not switch.is_dir():
        return []
    updates = [path.name for path in switch.rglob("*") if path.is_file() and UPDATE_NSP_RE.search(path.name)]
    if not updates:
        return []
    return [
        Check(
            "INFO",
            "Switch update NSPs",
            f"{len(updates)} title-update file(s) present, e.g. {updates[0][:70]}",
            "these contain no application and can never launch; do NOT delete them - "
            "Ryujinx references them by path. Mark them <hidden> in gamelist.xml, and apply "
            "one via right-click -> Manage Title Updates",
        )
    ]


def _supermodel_launcher() -> Check | None:
    """The two halves of the Model 3 workaround, both of which are load-bearing."""
    launcher = paths.retrodeck_root() / "ES-DE" / "custom_systems" / "supermodel-launch.sh"
    if not launcher.is_file():
        if (paths.roms_dir() / "model3").is_dir():
            return Check(
                "WARN",
                "Supermodel launcher",
                f"model3 ROMs exist but {launcher} is missing",
                "RetroDECK bundles no Model 3 emulator; the custom system needs this launcher",
            )
        return None
    try:
        text = launcher.read_text(errors="replace")
    except OSError as error:
        return Check("WARN", "Supermodel launcher", f"unreadable: {error}")
    has_wayland_unset = re.search(r"WAYLAND_DISPLAY=(\s|$|\\)", text) is not None
    has_cd = "cd " in text or "--directory" in text
    if has_wayland_unset and has_cd:
        return Check("PASS", "Supermodel launcher", "clears WAYLAND_DISPLAY and sets its working directory")
    missing = []
    if not has_wayland_unset:
        missing.append("WAYLAND_DISPLAY= (else 'OpenGL initialization failed: Unknown error')")
    if not has_cd:
        missing.append("a cd into the config dir (else Assets/ does not resolve)")
    return Check(
        "WARN",
        "Supermodel launcher",
        "workaround incomplete - missing " + " and ".join(missing),
        "do not remove either half of the workaround",
    )


def _esde_settings() -> Check | None:
    settings = paths.esde_settings()
    if not settings.is_file():
        return Check("INFO", "ES-DE settings", f"not present at {settings}")
    try:
        text = settings.read_text(errors="replace")
    except OSError:
        return None
    notes: list[str] = []
    hidden = re.search(r'name="ShowHiddenGames"\s+value="(\w+)"', text)
    if hidden and hidden.group(1).lower() == "true":
        notes.append("ShowHiddenGames=true, so update NSPs and hidden entries appear in the carousel")
    scrape = re.search(r'name="ScraperOverwriteData"\s+value="(\w+)"', text)
    if scrape and scrape.group(1).lower() == "true":
        notes.append("ScraperOverwriteData=true - ES-DE's own scraper will overwrite external metadata")
    if not notes:
        return Check("PASS", "ES-DE settings", "no setting that would fight an external scraper")
    return Check("WARN", "ES-DE settings", "; ".join(notes))


def collect() -> Report:
    report = Report("Emulation / RetroDECK")
    report.add(_running())
    report.extend(_layout())
    report.extend(_gamelists())
    report.extend(_path_prefix_trap())
    report.add(_esde_settings())
    report.extend(_log_scan())
    report.add(_bios_log())
    report.extend(_switch_updates())
    report.add(_supermodel_launcher())
    return report
