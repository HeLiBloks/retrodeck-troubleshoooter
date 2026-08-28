"""The command line. Read-only everywhere; exit 0 healthy / 1 warnings / 2 failures."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import emulation, env, flatpakq, inputs, kb_cli, osquery, paths, scraping
from .probe import Check, Report, exit_code, render, render_json

EPILOG = """\
groups:
  all         every group below (the default)
  env         whether a .env was found, and which keys it supplies
  os          SELinux, ostree, disks, brew, distrobox
  flatpak     app installs, sandbox reach to the ROM tree, overrides
  emulation   RetroDECK layout, gamelists, logs, BIOS, Switch, Model 3
  input       controllers, and the black-screen-after-loading symptom
  scraping    Skyscraper, credentials, resource cache, quota, coverage

knowledge base:
  rdtroubleshoot kb --help     recorded symptoms, their signatures, and their fixes
  rdtroubleshoot kb match LOG  match a log against every recorded signature
  --kb                         annotate each WARN/FAIL with the entries that cover it

environment:
  RETRODECK_HOME   the RetroDECK tree           (default ~/retrodeck)
  RETRODECK_ROMS   the ROM folder               (default $RETRODECK_HOME/roms)
  RETRODECK_ESDE   the ES-DE folder             (default $RETRODECK_HOME/ES-DE)
  RDT_ENV_FILE     an alternative .env location (default ./.env)
  NO_COLOR         disable colour

credentials:
  A .env is entirely optional - see .env_template. Without one, every check that needs
  privilege reports what it could not inspect and the exit code does not move. With one,
  RDT_SUDO_PASSWORD unlocks the full SELinux audit log and system Flatpak overrides.
  A secret is never printed and never placed on a command line; a group- or world-readable
  .env is reported as a FAILURE and its secrets are withheld. --no-env ignores the file.

Nothing in this tool writes a file, spends API quota, or starts an emulator, so it is
safe to run while RetroDECK is open. --probe-sandbox is the one exception to "no
subprocess of consequence": it starts an app's Flatpak *runtime* to run `sh`, which
launches no emulator and writes nothing, but does take a few seconds.
"""

GROUPS = ("env", "os", "flatpak", "emulation", "input", "scraping")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rdtroubleshoot",
        description="Read-only diagnostics for RetroDECK emulation and scraping on Bazzite.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "groups",
        nargs="*",
        default=["all"],
        help="which groups to run (default: all)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="only WARN and FAIL lines"
    )
    parser.add_argument(
        "--show-benign",
        action="store_true",
        help="include SELinux denials known to be normal on this host",
    )
    parser.add_argument(
        "--probe-sandbox",
        action="store_true",
        help="ask each Flatpak sandbox whether it can really read the ROM tree (slower)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="path to a retrodeck-scraper checkout, for .env and scrape logs",
    )
    parser.add_argument("--no-color", action="store_true", help="disable colour")
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="ignore any .env file, and skip every check that needs privilege",
    )
    parser.add_argument(
        "--kb",
        action="store_true",
        help="annotate each WARN/FAIL check with matching knowledge-base entries",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="read credentials from this file instead of ./.env",
    )
    parser.add_argument(
        "--guid",
        nargs=4,
        metavar=("BUSTYPE", "VENDOR", "PRODUCT", "VERSION"),
        help="derive a Ryujinx controller id from four hex sysfs ids and exit",
    )
    return parser


def _selected(names: list[str]) -> list[str]:
    if not names or "all" in names:
        return list(GROUPS)
    unknown = [name for name in names if name not in GROUPS]
    if unknown:
        raise SystemExit(f"unknown group(s): {', '.join(unknown)}\nknown: {', '.join(GROUPS)}")
    # Keep the canonical order regardless of how they were typed.
    return [name for name in GROUPS if name in names]


def annotate_from_kb(reports: list[Report]) -> None:
    """Point each WARN/FAIL at the knowledge-base entries that cover it.

    Matching is on the check's own name against entries carrying a `checker:` signature,
    which works only because a KB area IS a checker group - that coupling is what turns a
    finding into "and here is what we already know about it" rather than a dead end.

    A missing or malformed KB must not break a diagnostic run, so any failure here is
    swallowed: the checks the user asked for are more important than the annotation.
    """
    try:
        from . import kb

        entries = kb.load_all()
    except Exception:
        return
    if not entries:
        return
    for report in reports:
        annotated: list[Check] = []
        for check in report.checks:
            if check.level not in ("WARN", "FAIL"):
                annotated.append(check)
                continue
            matches = kb.match_text(entries, check.name + "\n" + check.detail, source="checker")
            notes: list[str] = []
            seen: set[str] = set()
            for match in matches:
                if match.entry.slug in seen:
                    continue
                seen.add(match.entry.slug)
                state = "fix known" if match.entry.state == "errors" else "open, no fix yet"
                notes.append(
                    f"known issue [{state}]: {match.entry.slug}"
                )
                notes.append(
                    f"  docs/kb/{match.entry.state}/{match.entry.area}/{match.entry.slug}.md"
                )
            annotated.append(check.with_notes(notes) if notes else check)
        report.checks = annotated


def main(argv: list[str] | None = None) -> int:
    # `kb` is a subcommand tree of its own, dispatched before the group parser so the
    # existing positional form (`rdtroubleshoot emulation input`) is untouched.
    if argv is None:
        import sys as _sys

        argv = _sys.argv[1:]
    if argv and argv[0] == "kb":
        kb_parser = argparse.ArgumentParser(prog="rdtroubleshoot")
        subparsers = kb_parser.add_subparsers(dest="command", required=True)
        kb_cli.add_parser(subparsers)
        kb_args = kb_parser.parse_args(argv)
        return kb_args.func(kb_args)

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.guid:
        from .inputs import controller_guid

        try:
            values = [int(value, 16) for value in args.guid]
        except ValueError:
            raise SystemExit("the four ids must be hexadecimal, as sysfs writes them")
        print(controller_guid(*values))
        return 0

    # Credentials are loaded once and passed down, so no module reads the file itself
    # and there is exactly one place that decides whether a secret may be used.
    creds = None if args.no_env else env.load(args.env_file)
    if creds is not None:
        env.apply_paths(creds)

    reports: list[Report] = []
    for group in _selected(args.groups):
        if group == "env":
            report = Report("Credentials")
            if creds is None:
                report.add(
                    Check("INFO", ".env", "ignored because --no-env was given")
                )
            else:
                report.extend(env.collect_checks(creds))
            reports.append(report)
        elif group == "os":
            reports.append(osquery.collect(show_benign=args.show_benign, creds=creds))
        elif group == "flatpak":
            reports.append(flatpakq.collect(probe=args.probe_sandbox, creds=creds))
        elif group == "emulation":
            reports.append(emulation.collect())
        elif group == "input":
            reports.append(inputs.collect())
        elif group == "scraping":
            reports.append(scraping.collect(repo=args.repo, creds=creds))

    if args.kb:
        annotate_from_kb(reports)

    if args.json:
        print(render_json(reports))
    else:
        colour = False if args.no_color else None
        print(render(reports, colour=colour, quiet=args.quiet))

    return exit_code([check for report in reports for check in report.checks])


def entrypoint() -> None:
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        # `rdtroubleshoot | head` must not print a traceback from the interpreter's
        # own flush on the way out.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        raise SystemExit(141)
    except KeyboardInterrupt:
        raise SystemExit(130)
