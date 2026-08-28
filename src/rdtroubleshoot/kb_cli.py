"""`rdtroubleshoot kb ...` — read and write the knowledge base.

Read commands are safe anywhere. The write commands (`new`, `sighting`, `promote`,
`commit`, `push`) touch the repository, and each carries the gate its own step needs:
`promote` needs a verification record, `commit` needs a clean lint and a green suite, and
`push` decides between a direct push and a pull request by probing what the credentials
can actually do.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from . import kb, kb_ops
from .probe import Check, Report, render


def _kb_root(args) -> Path:
    return Path(args.kb) if getattr(args, "kb", None) else kb.kb_root()


def _repo_root(args) -> Path:
    return Path(args.repo_root) if getattr(args, "repo_root", None) else kb_ops.repo_root()


def cmd_list(args) -> int:
    entries = kb.load_all(_kb_root(args))
    if args.area:
        entries = [e for e in entries if e.area == args.area]
    if not entries:
        print("no entries")
        return 0
    width = max(len(e.slug) for e in entries)
    for entry in entries:
        state = "FIX " if entry.state == "errors" else "OPEN"
        print(f"{state}  {entry.area:<9}  {entry.slug:<{width}}  {entry.title}")
    fixed = sum(1 for e in entries if e.state == "errors")
    print(f"\n{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}: {fixed} with a fix, {len(entries) - fixed} open")
    return 0


def cmd_search(args) -> int:
    entries = kb.search(kb.load_all(_kb_root(args)), args.term)
    if not entries:
        print(f"no entry mentions {args.term!r}")
        return 1
    for entry in entries:
        state = "FIX " if entry.state == "errors" else "OPEN"
        print(f"{state}  {entry.slug}  ({entry.area})")
        print(f"      {entry.title}")
        first = entry.tldr.split("\n\n")[0].replace("\n", " ")
        print(f"      {first[:160]}")
        print()
    return 0


def cmd_check(args) -> int:
    problems = kb.lint(_kb_root(args))
    if not problems:
        entries = kb.load_all(_kb_root(args))
        signatures = sum(len(e.signatures) for e in entries)
        print(f"knowledge base is clean: {len(entries)} entries, {signatures} signatures")
        return 0
    print(f"{len(problems)} problem(s):")
    for problem in problems:
        print(f"  {problem}")
    return 1


def cmd_match(args) -> int:
    """Match a log (or stdin) against every entry's signatures for that source."""
    entries = kb.load_all(_kb_root(args))
    if args.path == "-":
        import sys

        text = sys.stdin.read()
    else:
        path = Path(args.path)
        if not path.is_file():
            print(f"no such file: {path}")
            return 2
        from .probe import tail_lines

        text = "\n".join(tail_lines(path, limit=args.lines))
    matches = kb.match_text(entries, text, source=args.source)
    if not matches:
        print(f"no entry matches this {args.source} content")
        print("  If the symptom is real and unrecorded, that is a new case:")
        print("    rdtroubleshoot kb new --area <area> --slug <symptom-slug> --title '...'")
        return 1
    seen: set[str] = set()
    for item in matches:
        if item.entry.slug in seen:
            continue
        seen.add(item.entry.slug)
        state = "FIX " if item.entry.state == "errors" else "OPEN"
        print(f"{state}  {item.entry.slug}  ({item.entry.area})")
        print(f"      matched {item.signature.source}: {item.signature.pattern}")
        print(f"      {item.count} hit(s), last: {item.line[:120]}")
        print(f"      -> docs/kb/{item.entry.state}/{item.entry.area}/{item.entry.slug}.md")
        print()
    return 0


def cmd_new(args) -> int:
    try:
        path = kb_ops.new_entry(
            slug=args.slug, area=args.area, title=args.title, root=_kb_root(args)
        )
    except kb.KbError as error:
        print(f"error: {error}")
        return 2
    print(f"created {path}")
    print("Next:")
    print("  1. fill in the signatures, the symptom signature, and what is known")
    print(f"  2. add a row to docs/kb/backlog/INDEX.md pointing at {args.area}/{args.slug}.md")
    print("  3. rdtroubleshoot kb check")
    print(f"  4. rdtroubleshoot kb commit {args.slug}")
    return 0


def cmd_sighting(args) -> int:
    try:
        path = kb_ops.add_sighting(args.slug, args.note, root=_kb_root(args))
    except kb.KbError as error:
        print(f"error: {error}")
        return 2
    print(f"recorded a sighting in {path}")
    return 0


def cmd_promote(args) -> int:
    try:
        path = kb_ops.promote(args.slug, verified_by=args.verified_by, root=_kb_root(args))
    except kb.KbError as error:
        print(f"error: {error}")
        return 2
    print(f"promoted to {path}")
    print("  INDEX rows moved, and an eval fixture was scaffolded if none existed.")
    print("  Fill in the Fix and Verification sections, then:")
    print(f"    rdtroubleshoot kb check && rdtroubleshoot kb commit {args.slug}")
    return 0


def cmd_commit(args) -> int:
    ok, detail = kb_ops.commit(
        args.slugs, root=_repo_root(args), run_tests=not args.skip_tests
    )
    print(detail)
    if not ok:
        return 1
    if args.push:
        action, info = kb_ops.push_or_pr(
            root=_repo_root(args), slug=args.slugs[0] if args.slugs else ""
        )
        print(f"{action}: {info}")
        return 0 if action == "pushed" else 1
    return 0


def cmd_push(args) -> int:
    action, info = kb_ops.push_or_pr(root=_repo_root(args), slug=args.slug or "")
    print(f"{action}: {info}")
    return 0 if action == "pushed" else 1


def cmd_gate(args) -> int:
    verdict = kb_ops.gate(root=_repo_root(args), run_tests=not args.skip_tests)
    if verdict.ok:
        print("gate passes: lint clean" + ("" if args.skip_tests else " and suite green"))
        return 0
    print("gate BLOCKS a commit:")
    for reason in verdict.reasons:
        print(f"  {reason}")
    return 1


def add_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "kb",
        help="read and write the knowledge base",
        description="Knowledge base: recorded symptoms, their signatures, and their fixes.",
    )
    parser.add_argument("--kb", help="path to docs/kb (default: alongside this package)")
    parser.add_argument("--repo-root", help="repository root, for commit and push")
    sub = parser.add_subparsers(dest="kb_command", required=True)

    p = sub.add_parser("list", help="every entry, fixed first")
    p.add_argument("--area", choices=kb.AREAS)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("search", help="entries mentioning a term")
    p.add_argument("term")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("check", help="lint the knowledge base (this is the commit gate)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("match", help="match a log against every entry's signatures")
    p.add_argument("path", help="a log file, or - for stdin")
    p.add_argument(
        "--source",
        default="retrodeck-log",
        choices=[s for s in kb.SOURCES if s != "symptom"],
        help="which signature source this content is (default: retrodeck-log)",
    )
    p.add_argument("--lines", type=int, default=6000, help="how many trailing lines to read")
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("new", help="scaffold a new backlog entry")
    p.add_argument("--slug", required=True, help="lower-kebab-case, naming the SYMPTOM")
    p.add_argument("--area", required=True, choices=kb.AREAS)
    p.add_argument("--title", required=True)
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("sighting", help="record a recurrence on an existing entry")
    p.add_argument("slug")
    p.add_argument("note", help="what was seen, and where")
    p.set_defaults(func=cmd_sighting)

    p = sub.add_parser("promote", help="move a backlog entry to errors/ (needs verification)")
    p.add_argument("slug")
    p.add_argument(
        "--verified-by",
        required=True,
        dest="verified_by",
        help="how the fix was confirmed: a check name, a command, or an observation",
    )
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("gate", help="report whether a commit would be allowed")
    p.add_argument("--skip-tests", action="store_true")
    p.set_defaults(func=cmd_gate)

    p = sub.add_parser("commit", help="commit docs/kb changes, if the gate passes")
    p.add_argument("slugs", nargs="*", help="slugs this change is about, for the message")
    p.add_argument("--push", action="store_true", help="push, or prepare a PR branch")
    p.add_argument("--skip-tests", action="store_true")
    p.set_defaults(func=cmd_commit)

    p = sub.add_parser("push", help="push to main, or prepare a branch and PR instructions")
    p.add_argument("--slug", help="names the branch if a PR is needed")
    p.set_defaults(func=cmd_push)
