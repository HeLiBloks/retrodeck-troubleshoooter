"""Optional credentials from a `.env` file, for the checks that need privilege.

Most of this tool answers its questions as an ordinary user. A few cannot: the audit log
under `/var/log/audit` is root-only, so `ausearch` sees nothing without it, and system
Flatpak overrides live under `/var/lib/flatpak` where a user may not read. Those checks
degrade to INFO by default and only run when a `.env` supplies what they need.

Three rules, and each of them is the reason a line here looks the way it does:

- **A secret is never printed, never logged, and never placed on a command line.** Argv is
  world-readable through `/proc`, so a sudo password goes down the child's stdin via
  `sudo -S` and nowhere else. `Credentials.__repr__` is overridden because the default one
  would put the password in a traceback.
- **A world-readable `.env` is a finding, not a detail.** The file holds a root password;
  if its mode exposes it, the tool says so and *still refuses to use it*, because using it
  would validate a hazard the user has not been told about yet.
- **Absent is not broken.** No `.env`, or a `.env` with only some keys, is the normal case.
  Those checks say what they could not inspect and why, and the exit code does not move.

The parser tolerates what people actually write: `export KEY=value`, `KEY = value`,
single or double quotes (embedded quotes preserved), `#` comments, and blank lines.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

# Keys the tool understands. Anything else in the file is ignored rather than rejected,
# so a shared .env can carry unrelated settings.
KNOWN_KEYS = (
    "RDT_SUDO_PASSWORD",
    "RDT_SSH_TARGET",
    "RDT_RETRODECK_HOME",
    "RDT_ROMS",
    "RDT_ESDE",
    "SS_USER",
    "SS_PASS",
)
SECRET_KEYS = frozenset({"RDT_SUDO_PASSWORD", "SS_PASS"})

_LINE_RE = re.compile(r"""^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$""")


@dataclass
class Credentials:
    """Parsed `.env` contents plus the findings about the file itself."""

    values: dict[str, str] = field(default_factory=dict)
    path: Path | None = None
    insecure_mode: str | None = None  # set when the file is group/world readable
    notes: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        # The default dataclass repr would render the password into any traceback.
        keys = ",".join(sorted(self.values))
        return f"Credentials(path={self.path!s}, keys=[{keys}], insecure={bool(self.insecure_mode)})"

    __str__ = __repr__

    def get(self, key: str) -> str | None:
        """A value, or None. A secret from an insecurely-moded file is withheld.

        Withholding rather than warning-and-using is deliberate: acting on the password
        would confirm to the user that everything is fine, which is the opposite of what
        a world-readable root password means.
        """
        if key in SECRET_KEYS and self.insecure_mode:
            return None
        value = self.values.get(key)
        return value or None

    @property
    def can_sudo(self) -> bool:
        return self.get("RDT_SUDO_PASSWORD") is not None

    def redacted(self) -> dict[str, str]:
        """Every key, with secrets shown as a placeholder. Safe to print."""
        return {
            key: ("<set>" if key in SECRET_KEYS else value)
            for key, value in sorted(self.values.items())
        }


def _unquote(raw: str) -> str:
    """Strip one matching pair of surrounding quotes, preserving what is inside."""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            continue
        key, raw = match.group(1), match.group(2)
        # An unquoted trailing comment is not part of the value; a quoted one is.
        if raw[:1] not in "\"'":
            raw = raw.split(" #", 1)[0].rstrip()
        values[key] = _unquote(raw)
    return values


def default_path() -> Path:
    """`$RDT_ENV_FILE`, else `.env` beside the repository root."""
    override = os.environ.get("RDT_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / ".env"


def load(path: Path | None = None) -> Credentials:
    """Read a `.env`, or return an empty Credentials when there is none."""
    target = path or default_path()
    creds = Credentials(path=target)
    if not target.is_file():
        creds.path = None
        return creds
    try:
        text = target.read_text(errors="replace")
    except OSError as error:
        creds.notes.append(f"{target} could not be read: {error}")
        return creds
    try:
        mode = target.stat().st_mode
        if mode & (stat.S_IRGRP | stat.S_IROTH):
            creds.insecure_mode = stat.filemode(mode)
    except OSError:
        pass
    creds.values = {key: value for key, value in parse(text).items() if value}
    unknown = sorted(set(creds.values) - set(KNOWN_KEYS))
    if unknown:
        creds.notes.append(f"ignored unrecognised key(s): {', '.join(unknown)}")
    return creds


def apply_paths(creds: Credentials) -> None:
    """Let the `.env` supply the RetroDECK locations, without overriding a real env var.

    Precedence is flag > environment > .env, matching the scraper this came from, so a
    one-off `RETRODECK_ROMS=... rdtroubleshoot` still wins.
    """
    for key, target in (
        ("RDT_RETRODECK_HOME", "RETRODECK_HOME"),
        ("RDT_ROMS", "RETRODECK_ROMS"),
        ("RDT_ESDE", "RETRODECK_ESDE"),
    ):
        value = creds.get(key)
        if value and not os.environ.get(target):
            os.environ[target] = os.path.expanduser(value)


def sudo_run(argv: list[str], creds: Credentials, *, timeout: int = 25):
    """Run `argv` under sudo, feeding the password on stdin. None when unavailable.

    `sudo -S` reads the password from stdin and `-p ''` suppresses the prompt, so nothing
    of the secret reaches argv or the terminal. Returns the same Result type as probe.run.
    """
    import subprocess

    from .probe import Result, have

    password = creds.get("RDT_SUDO_PASSWORD")
    if password is None or not have("sudo"):
        return None
    try:
        completed = subprocess.run(
            ["sudo", "-S", "-p", "", *argv],
            input=password + "\n",
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    # sudo writes its own failure to stderr; do not echo that verbatim anywhere a
    # password could be quoted back.
    return Result(completed.returncode == 0, completed.returncode, completed.stdout, completed.stderr)


def collect_checks(creds: Credentials) -> list:
    """What the tool wants the user to know about the .env itself."""
    from .probe import Check

    checks: list[Check] = []
    if creds.path is None:
        return [
            Check(
                "INFO",
                ".env",
                "no .env file; privileged checks will be skipped",
                "cp .env_template .env && chmod 600 .env   # optional",
            )
        ]
    if creds.insecure_mode:
        checks.append(
            Check(
                "FAIL",
                ".env permissions",
                f"{creds.path} is {creds.insecure_mode} - group/world readable while holding a "
                "password. Secrets from it are being WITHHELD until this is fixed",
                f"chmod 600 {creds.path}",
            )
        )
    else:
        checks.append(
            Check("PASS", ".env", f"{creds.path}, keys: {', '.join(creds.redacted()) or 'none'}"))
    for note in creds.notes:
        checks.append(Check("INFO", ".env", note))
    return checks
