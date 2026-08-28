"""Scraping: Skyscraper, credentials, the resource cache, and quota.

Every check here stands for a failure the parent project already paid for:

- **`userCreds="user:"` is worse than anonymous.** Skyscraper sends an empty password on
  every request, login is refused, and the run scrapes nothing while repeated bad logins
  carry a blacklist risk. It once cost a silent 4-5 hour nohup'd run. FAIL, not WARN.
- **A 52-byte stub `db.xml`** means that platform's cache is empty, so a `generate` there
  has nothing to publish and needs a quota-spending gather first. Knowing beforehand is
  the difference between a plan and a surprise.
- **Backups pile up.** 105 files and 113 MiB had accumulated under the gamelists before
  anyone looked. Counted on the digits-only suffixes the rotation actually owns, because a
  hand-labelled checkpoint is one it may not delete - counting those made the parent's
  check WARN permanently while the rotation worked exactly as specified.
- **Quota exhaustion exits 0.** All four messages Skyscraper prints before giving up leave
  the exit status at zero, so the log text is the only signal there is.
- **Descriptions were never the whole gap.** A folder reading 98% described can be 45%
  un-genred. Coverage is counted per tag for that reason.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path

from . import emulation, paths
from .probe import Check, Report, have, home, human, run

# Skyscraper writes about this much for a platform it has never gathered for.
CACHE_STUB_BYTES = 256
KEEP_BACKUPS = 3
MAX_BACKUPS_PER_SYSTEM = KEEP_BACKUPS + 1
USER_CREDS_RE = re.compile(r'^\s*userCreds\s*=\s*"(.*)"\s*$')
# Digits-only suffixes are the ones the rotation owns; a labelled checkpoint is not.
ROTATED_BACKUP_RE = re.compile(r"^gamelist\.xml\.bak\.\d+$")
# The full sentences Skyscraper prints before giving up. Short substrings both missed
# two of these and false-positived on game descriptions containing "Get a bigger quota!".
QUOTA_MARKERS = (
    "you have exceeded your daily quota",
    "the screenscraper api is currently closed",
    "currently closed or too busy",
    "maximum number of requests per day",
)


def _skyscraper() -> Check:
    found = run(["sh", "-c", "command -v Skyscraper"])
    if found is not None and found.ok and found.text:
        return Check("PASS", "Skyscraper", found.text.splitlines()[0])
    local = home() / "skysource" / "Skyscraper"
    if local.is_file():
        return Check(
            "WARN",
            "Skyscraper",
            f"not on PATH but present at {local}",
            f'export PATH="{local.parent}:$PATH"',
        )
    if not have("distrobox"):
        return Check("WARN", "Skyscraper", "not on PATH and distrobox is unavailable")
    result = run(["distrobox", "list", "--no-color"], timeout=30)
    if result is not None and result.ok and "skyscraper" in result.out:
        state = "Up" if re.search(r"skyscraper.*\|\s*Up", result.out) else "stopped"
        return Check(
            "WARN",
            "Skyscraper",
            f"not on PATH; the 'skyscraper' distrobox exists but is {state}",
            "distrobox enter -n skyscraper -- Skyscraper --help",
        )
    return Check("WARN", "Skyscraper", "not on PATH and no 'skyscraper' distrobox exists")


def _mode_note(path: Path) -> str | None:
    try:
        mode = path.stat().st_mode
    except OSError:
        return None
    if mode & (stat.S_IRGRP | stat.S_IROTH):
        return f"mode {stat.filemode(mode)} is group/world readable"
    return None


def _credentials() -> list[Check]:
    checks: list[Check] = []
    config = paths.skyscraper_home() / "config.ini"
    if not config.is_file():
        return [
            Check(
                "INFO",
                "ScreenScraper creds",
                f"no {config}; gathering will run anonymously (1 thread, often refused)",
            )
        ]
    try:
        text = config.read_text(errors="replace")
    except OSError as error:
        return [Check("WARN", "ScreenScraper creds", f"{config} unreadable: {error}")]
    creds: str | None = None
    for line in text.splitlines():
        match = USER_CREDS_RE.match(line)
        if match:
            creds = match.group(1)
            break
    if creds is None:
        checks.append(Check("INFO", "ScreenScraper creds", "no userCreds line; runs will be anonymous"))
    elif ":" not in creds:
        checks.append(Check("FAIL", "ScreenScraper creds", "userCreds has no ':' separator"))
    else:
        user, _, password = creds.partition(":")
        if not user or not password:
            missing = "username" if not user else "password"
            checks.append(
                Check(
                    "FAIL",
                    "ScreenScraper creds",
                    f"userCreds is half-set (no {missing}) - this is WORSE than anonymous: "
                    "every request sends an empty field, login is refused, and repeated bad "
                    "logins risk a blacklist",
                    "fix .env and re-run the scraper's `creds` subcommand",
                )
            )
        else:
            # Never print the password, not even its length.
            hazard = [c for c in password if c in '"$;><&|`\\']
            if hazard:
                checks.append(
                    Check(
                        "WARN",
                        "ScreenScraper creds",
                        f"set for '{user}', but the password contains shell/URL-hazardous characters "
                        f"({''.join(sorted(set(hazard)))}) and Skyscraper does not URL-encode it",
                        "use an alphanumeric password; ';' can act as a query separator server-side",
                    )
                )
            else:
                checks.append(Check("PASS", "ScreenScraper creds", f"set for '{user}'"))
    note = _mode_note(config)
    if note:
        checks.append(
            Check("WARN", "config.ini permissions", f"{note} and it holds the password in cleartext", f"chmod 600 {config}")
        )
    return checks


def _env_file(repo: Path | None) -> Check | None:
    candidates = [path for path in ((repo / ".env") if repo else None, home() / "apps/retrodeck-scraper/.env") if path]
    for path in candidates:
        if path and path.is_file():
            note = _mode_note(path)
            if note:
                return Check("WARN", ".env permissions", f"{path}: {note}", f"chmod 600 {path}")
            return Check("PASS", ".env permissions", f"{path} is owner-only")
    return None


def _resource_cache() -> list[Check]:
    cache = paths.skyscraper_home() / "cache"
    if not cache.is_dir():
        return [Check("INFO", "Resource cache", f"no {cache}; every generate needs a gather first")]
    stubs: list[str] = []
    real: list[tuple[str, int]] = []
    for platform in sorted(cache.iterdir()):
        db = platform / "db.xml"
        if not db.is_file():
            if platform.is_dir():
                stubs.append(f"{platform.name} (no db.xml)")
            continue
        try:
            size = db.stat().st_size
        except OSError:
            continue
        if size <= CACHE_STUB_BYTES:
            stubs.append(platform.name)
        else:
            real.append((platform.name, size))
    checks: list[Check] = []
    if real:
        top = ", ".join(f"{name} {human(size)}" for name, size in sorted(real, key=lambda r: -r[1])[:5])
        checks.append(Check("PASS", "Resource cache", f"{len(real)} platform(s) with content - {top}"))
    if stubs:
        checks.append(
            Check(
                "INFO",
                "Resource cache stubs",
                f"{len(stubs)} platform(s) have an empty cache: {', '.join(stubs[:8])}",
                "a `generate` for these publishes nothing; they need a quota-spending gather first",
            )
        )
    return checks


def _backups() -> Check | None:
    listing = paths.gamelists_dir()
    if not listing.is_dir():
        return None
    worst: tuple[str, int] | None = None
    total = 0
    total_bytes = 0
    labelled = 0
    for system in sorted(listing.iterdir()):
        if not system.is_dir():
            continue
        rotated = [path for path in system.glob("gamelist.xml.bak.*") if ROTATED_BACKUP_RE.match(path.name)]
        labelled += len([path for path in system.glob("gamelist.xml.bak.*") if not ROTATED_BACKUP_RE.match(path.name)])
        total += len(rotated)
        for path in rotated:
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass
        if rotated and (worst is None or len(rotated) > worst[1]):
            worst = (system.name, len(rotated))
    if not total:
        return Check("PASS", "Gamelist backups", "none, or all hand-labelled")
    detail = f"{total} rotated file(s), {human(total_bytes)}"
    if labelled:
        detail += f" ({labelled} hand-labelled and kept by hand, not counted)"
    if worst and worst[1] > MAX_BACKUPS_PER_SYSTEM:
        return Check(
            "WARN",
            "Gamelist backups",
            detail + f"; '{worst[0]}' has {worst[1]}, above the rotation's {MAX_BACKUPS_PER_SYSTEM}",
            "something wrote a gamelist without rotating",
        )
    return Check("PASS", "Gamelist backups", detail)


def _quota(repo: Path | None) -> list[Check]:
    """Quota exhaustion in any scrape log. All four messages exit 0, so text is the signal."""
    roots = [path for path in (repo, home() / "apps/retrodeck-scraper") if path and path.is_dir()]
    logs: list[Path] = []
    for root in roots:
        logs.extend(sorted(root.glob("*.log")))
    if not logs:
        return []
    hits: list[str] = []
    for log in logs[-6:]:
        from .probe import tail_lines

        text = " ".join(tail_lines(log, limit=3000)).lower()
        collapsed = re.sub(r"\s+", " ", text)
        for marker in QUOTA_MARKERS:
            if marker in collapsed:
                hits.append(f"{log.name}: '{marker}'")
                break
    if not hits:
        return [Check("PASS", "Quota markers", f"none in {len(logs)} scrape log(s)")]
    return [
        Check(
            "WARN",
            "Quota markers",
            "; ".join(hits),
            "the run exited 0 regardless; gather again tomorrow with --flags onlymissing, "
            "or generate from cache now at no API cost",
        )
    ]


# A folder small enough that its whole gap is a handful of tags is not a coverage
# problem, and six WARN lines for nine missing tags is the chatter that teaches a user to
# ignore the exit code. Measured on the box: doom, dragon32, neogeocd, pc, quake and
# windows3x each hold 1-4 entries, and most are folders the scraper deliberately ignores
# because they are not Skyscraper platforms at all.
MIN_ENTRIES_TO_WARN = 8
DESC_WARN_RATIO = 0.75


def _coverage() -> list[Check]:
    """Per-tag counts per system, worst-described first.

    Counting the structured tags separately is the point: a folder can read 98% described
    and 45% un-genred at the same time, which is how mame looked before its filename
    bridge ran.
    """
    rows = emulation.coverage()
    if not rows:
        return []
    checks: list[Check] = []
    incomplete = 0
    small: list[str] = []
    for system, count, tags in rows:
        gaps = [
            f"{tag} {tags[tag]}/{count}"
            for tag in ("desc", "genre", "publisher", "players")
            if tags[tag] < count
        ]
        if not gaps:
            continue
        incomplete += 1
        if count < MIN_ENTRIES_TO_WARN:
            small.append(f"{system} ({count})")
            continue
        if len(checks) >= 6:
            continue
        ratio = tags["desc"] / count if count else 1.0
        level = "WARN" if ratio < DESC_WARN_RATIO else "INFO"
        checks.append(Check(level, f"Coverage ({system})", f"{count} entries - " + ", ".join(gaps)))
    if small:
        checks.append(
            Check(
                "INFO",
                "Coverage (small folders)",
                f"{len(small)} folder(s) under {MIN_ENTRIES_TO_WARN} entries have gaps: {', '.join(small[:8])}",
            )
        )
    shown = len([c for c in checks if c.name.startswith("Coverage (") and "small" not in c.name])
    if incomplete > shown + len(small):
        checks.append(
            Check("INFO", "Coverage", f"{incomplete - shown - len(small)} further system(s) with gaps not shown")
        )
    complete = [system for system, count, tags in rows if all(tags[tag] == count for tag in ("desc", "genre"))]
    if complete:
        checks.append(
            Check(
                "PASS",
                "Coverage",
                f"{len(complete)} system(s) fully described and genred: {', '.join(complete[:8])}",
            )
        )
    return checks


def _env_creds_crosscheck(creds) -> Check | None:
    """Does the username in `.env` match the one Skyscraper will actually send?

    A mismatch is the quiet version of the half-credential failure: the run authenticates
    as a different account, or as nobody, and still exits 0.
    """
    if creds is None:
        return None
    declared = creds.get("SS_USER")
    if not declared:
        return None
    config = paths.skyscraper_home() / "config.ini"
    if not config.is_file():
        return Check(
            "INFO",
            "ScreenScraper creds",
            f".env names user '{declared}' but there is no config.ini for Skyscraper to read",
        )
    try:
        text = config.read_text(errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        match = USER_CREDS_RE.match(line)
        if match:
            configured = match.group(1).partition(":")[0]
            if configured and configured != declared:
                return Check(
                    "WARN",
                    "ScreenScraper creds",
                    f"config.ini will send '{configured}' but .env names '{declared}'",
                    "the run authenticates as whoever is in config.ini, not .env",
                )
            return None
    return None


def collect(*, repo: Path | None = None, creds=None) -> Report:
    report = Report("Scraping")
    report.add(_skyscraper())
    report.extend(_credentials())
    report.add(_env_creds_crosscheck(creds))
    report.add(_env_file(repo))
    report.extend(_resource_cache())
    report.add(_backups())
    report.extend(_quota(repo))
    report.extend(_coverage())
    return report
