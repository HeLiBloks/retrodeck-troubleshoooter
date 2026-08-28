"""Check levels, the report, and the shell helpers every probe group shares.

Two rules the whole tool obeys, both learned from the scraper this was extracted from:

- **Nothing here writes anything.** No gamelist, no config, no media, no network. That is
  what makes it safe to run while RetroDECK is open, which is exactly when a user wants
  to ask what is wrong.
- **A state is not a fault.** RetroDECK being open, `/` being 100% full on an ostree
  composefs, SELinux denying sshd a control socket - all normal here. A checker that
  reports those as problems trains its user to ignore it, so the 0/1/2 exit contract is
  worth nothing. Anything normal-but-worth-knowing is INFO.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

# Ordered worst-last so max() picks the summary level.
LEVELS = ("INFO", "PASS", "WARN", "FAIL")
_RANK = {name: index for index, name in enumerate(LEVELS)}

EXIT_HEALTHY = 0
EXIT_WARNINGS = 1
EXIT_FAILURES = 2


@dataclass(frozen=True, slots=True)
class Check:
    """One finding. `fix` is printed only when there is something to type."""

    level: str
    name: str
    detail: str
    fix: str = ""

    def __post_init__(self) -> None:
        if self.level not in _RANK:
            raise ValueError(f"unknown level {self.level!r}")


@dataclass
class Report:
    group: str
    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check | None) -> None:
        if check is not None:
            self.checks.append(check)

    def extend(self, checks: Iterable[Check | None]) -> None:
        for check in checks:
            self.add(check)


def exit_code(checks: Sequence[Check]) -> int:
    if any(check.level == "FAIL" for check in checks):
        return EXIT_FAILURES
    if any(check.level == "WARN" for check in checks):
        return EXIT_WARNINGS
    return EXIT_HEALTHY


_COLOURS = {"PASS": "32", "WARN": "33", "FAIL": "31", "INFO": "36"}


def _colour(level: str, text: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{_COLOURS[level]}m{text}\033[0m"


def render(reports: Sequence[Report], *, colour: bool | None = None, quiet: bool = False) -> str:
    """Human-readable output. `quiet` drops PASS and INFO, leaving only what to act on."""
    if colour is None:
        colour = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
    lines: list[str] = []
    for report in reports:
        shown = [c for c in report.checks if not quiet or c.level in ("WARN", "FAIL")]
        if not shown:
            continue
        lines.append("")
        lines.append(f"== {report.group} ==")
        width = max(len(c.name) for c in shown)
        for check in shown:
            tag = _colour(check.level, f"{check.level:<4}", enabled=colour)
            lines.append(f"{tag}  {check.name:<{width}}  {check.detail}")
            if check.fix:
                lines.append(f"{'':<6}{'':<{width}}  -> {check.fix}")
    every = [c for report in reports for c in report.checks]
    if every:
        tally = {level: sum(1 for c in every if c.level == level) for level in LEVELS}
        lines.append("")
        lines.append(
            "{FAIL} failure(s), {WARN} warning(s), {PASS} pass(es), {INFO} note(s)".format(**tally)
        )
    return "\n".join(lines).lstrip("\n")


def render_json(reports: Sequence[Report]) -> str:
    import json

    payload = [
        {
            "group": report.group,
            "checks": [
                {"level": c.level, "name": c.name, "detail": c.detail, "fix": c.fix}
                for c in report.checks
            ],
        }
        for report in reports
    ]
    return json.dumps(payload, indent=2)


# --- shell helpers ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    code: int
    out: str
    err: str

    @property
    def text(self) -> str:
        return self.out.strip()


def run(argv: Sequence[str], *, timeout: int = 15) -> Result | None:
    """Run a command, or return None when it could not run at all.

    None and a non-zero Result are different answers and callers depend on the
    difference: "there is no such command here" is usually INFO, while "the command ran
    and said no" is usually the finding.
    """
    if shutil.which(argv[0]) is None and not Path(argv[0]).is_absolute():
        return None
    try:
        completed = subprocess.run(
            list(argv),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return Result(completed.returncode == 0, completed.returncode, completed.stdout, completed.stderr)


def have(command: str) -> bool:
    return shutil.which(command) is not None


def human(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"


def home() -> Path:
    """The user's home as spelled by $HOME, deliberately not resolved.

    On Bazzite `$HOME` is `/home/retro`, a symlink to `/var/home/retro`. The two
    spellings are not interchangeable in a gamelist, and resolving here is precisely how
    the scraper once lost 7 descriptions and 22 playcount tags. Anything that needs the
    real path asks for it explicitly.
    """
    return Path(os.environ.get("HOME", str(Path.home())))


def tail_lines(path: Path, *, limit: int = 4000, block: int = 1 << 20) -> list[str]:
    """The last `limit` lines, read from the end so a 200 MB log costs one block.

    Decoded with errors="replace": RetroDECK's log interleaves emulator stdout and is
    not reliably UTF-8.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            end = handle.tell()
            chunks: list[bytes] = []
            newlines = 0
            while end > 0 and newlines <= limit:
                step = min(block, end)
                end -= step
                handle.seek(end)
                data = handle.read(step)
                newlines += data.count(b"\n")
                chunks.append(data)
    except OSError:
        return []
    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return text.splitlines()[-limit:]


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)
