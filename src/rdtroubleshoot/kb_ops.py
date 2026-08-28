"""Writing to the knowledge base: file, sight, promote, commit, push.

The rule this module exists to enforce is the one a human forgets under pressure:
**a fix is published only once it has been verified.** So the gate is code, not a
convention. `promote` refuses without a verification record, `commit` refuses on a lint
failure or a red suite, and `push` decides between a direct push and a pull request by
*probing what the credentials can actually do* rather than by comparing a username.

The split between what commits freely and what does not is deliberate:

- **Evidence commits freely.** A sighting or a new `backlog/` entry is an observation -
  "this happened, here is the log" - and being wrong about an observation costs a later
  correction, not a bad fix in someone's hands. Recording one-offs precisely is the only
  thing that makes a second sighting recognisable.
- **A fix does not.** Promotion to `errors/` means the next person is told to *do*
  something. That needs the symptom seen, the fix applied, and the symptom confirmed gone.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import kb


def today() -> str:
    return dt.date.today().isoformat()


def repo_root(start: Path | None = None) -> Path:
    return start or Path(__file__).resolve().parents[2]


def _git(args: list[str], *, root: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        stdin=subprocess.DEVNULL,
        errors="replace",
    )


# --- creating and updating entries ------------------------------------------------


def new_entry(
    *,
    slug: str,
    area: str,
    title: str,
    root: Path | None = None,
    state: str = "backlog",
) -> Path:
    """Scaffold an entry from the template. Always `backlog/` unless told otherwise.

    Defaulting to backlog is the lifecycle in one line: a case is born without a fix, and
    reaches `errors/` only by promotion.
    """
    base = root or kb.kb_root()
    if not kb.SLUG_RE.match(slug):
        raise kb.KbError(f"slug {slug!r} must be lower-kebab-case")
    if area not in kb.AREAS:
        raise kb.KbError(f"area {area!r} must be one of {', '.join(kb.AREAS)}")
    template = base / f"{state}" / "_template.md"
    if not template.is_file():
        raise kb.KbError(f"no template at {template}")
    target = base / state / area / f"{slug}.md"
    if target.exists():
        raise kb.KbError(f"{target} already exists - add a sighting instead")
    target.parent.mkdir(parents=True, exist_ok=True)
    text = (
        template.read_text()
        .replace("<slug>", slug)
        .replace("<area>", area)
        .replace("<title naming the symptom>", title)
        .replace("YYYY-MM-DD", today())
    )
    target.write_text(text)
    return target


def add_sighting(slug: str, note: str, *, root: Path | None = None) -> Path:
    """Append a dated sighting and move `last_confirmed` forward.

    A recurrence is the single most useful thing to record: it turns a one-off into a
    pattern, and on a `backlog/` entry the second sighting is the cue to go and fix it.
    """
    base = root or kb.kb_root()
    entry = find_entry(slug, root=base)
    text = entry.path.read_text()
    stamp = today()
    text = re.sub(
        r"^last_confirmed:.*$", f"last_confirmed: {stamp}", text, count=1, flags=re.MULTILINE
    )
    line = f"- **{stamp}** — {note.strip()}\n"
    if "### Sightings" in text:
        head, _, tail = text.partition("### Sightings")
        body_lines = tail.split("\n")
        # Insert after the heading and any immediately following blank line.
        insert_at = 1
        while insert_at < len(body_lines) and not body_lines[insert_at].strip():
            insert_at += 1
        body_lines.insert(insert_at, line.rstrip("\n"))
        text = head + "### Sightings" + "\n".join(body_lines)
    else:
        text = text.rstrip("\n") + "\n\n### Sightings\n\n" + line
    entry.path.write_text(text)
    return entry.path


def find_entry(slug: str, *, root: Path | None = None) -> kb.Entry:
    for entry in kb.load_all(root):
        if entry.slug == slug:
            return entry
    raise kb.KbError(f"no entry with slug {slug!r}")


def _move_index_row(base: Path, slug: str) -> bool:
    """Move a slug's INDEX rows from backlog to errors. True when any row moved.

    Promotion has to carry the routing with it, or the entry becomes invisible in its new
    home while a stale row still points into the old one.
    """
    src = kb.index_path(base, "backlog")
    dst = kb.index_path(base, "errors")
    if not src.is_file() or not dst.is_file():
        return False
    src_text = src.read_text()
    keep: list[str] = []
    moved: list[str] = []
    for line in src_text.splitlines():
        if re.search(rf"\]\([^)]*{re.escape(slug)}\.md\)", line):
            moved.append(line.replace("(backlog/", "(errors/"))
        else:
            keep.append(line)
    if not moved:
        return False
    src.write_text("\n".join(keep).rstrip("\n") + "\n")
    dst_text = dst.read_text().rstrip("\n")
    dst.write_text(dst_text + "\n" + "\n".join(moved) + "\n")
    return True


def promote(
    slug: str,
    *,
    verified_by: str,
    root: Path | None = None,
) -> Path:
    """Move an entry from `backlog/` to `errors/`, stamping the verification.

    `verified_by` is mandatory and free text on purpose: it may be a check name
    ("rdtroubleshoot input"), a command, or an observation ("game reached the title
    screen"). What matters is that a later reader can tell *how* anyone knew it worked -
    an unverified fix in an errors/ entry is worse than no entry, because it is trusted.
    """
    base = root or kb.kb_root()
    if not verified_by.strip():
        raise kb.KbError("promotion needs verified_by: how was the fix confirmed?")
    entry = find_entry(slug, root=base)
    if entry.state == "errors":
        raise kb.KbError(f"{slug} is already in errors/")
    target = base / "errors" / entry.area / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)

    text = entry.path.read_text()
    stamp = today()
    text = re.sub(r"^status:.*$", "status: fixed", text, count=1, flags=re.MULTILINE)
    text = re.sub(
        r"^last_confirmed:.*$", f"last_confirmed: {stamp}", text, count=1, flags=re.MULTILINE
    )
    if re.search(r"^verified:", text, re.MULTILINE):
        text = re.sub(r"^verified:.*$", f"verified: {stamp}", text, count=1, flags=re.MULTILINE)
        text = re.sub(
            r"^verified_by:.*$", f"verified_by: {verified_by}", text, count=1, flags=re.MULTILINE
        )
    else:
        text = re.sub(
            r"^(last_confirmed:.*)$",
            rf"\1\nverified: {stamp}\nverified_by: {verified_by}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    target.write_text(text)
    entry.path.unlink()
    _move_index_row(base, slug)

    fixture = base / "evals" / f"{slug}.md"
    if not fixture.is_file():
        _scaffold_eval(base, slug, entry.area, verified_by)
    return target


def _scaffold_eval(base: Path, slug: str, area: str, verified_by: str) -> Path:
    template = base / "evals" / "_template.md"
    target = base / "evals" / f"{slug}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    if template.is_file():
        text = (
            template.read_text()
            .replace("<slug>", slug)
            .replace("<area>", area)
            .replace("YYYY-MM-DD", today())
            .replace("<verified_by>", verified_by)
        )
    else:
        text = f"---\nslug: {slug}\nkb_entry: ../errors/{area}/{slug}.md\nrecorded: {today()}\n---\n"
    target.write_text(text)
    return target


# --- the commit gate --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GateResult:
    ok: bool
    reasons: list[str]


def gate(*, root: Path | None = None, run_tests: bool = True) -> GateResult:
    """Everything that must hold before a KB change may be committed.

    The lint is the substantive half - it is what enforces the promotion gate, the INDEX
    rows and the signature validity. The suite is included because a KB change can break
    it (a malformed entry fails the lint test), and finding that out after the push is
    strictly worse.
    """
    base_repo = repo_root(root)
    reasons: list[str] = []
    problems = kb.lint(base_repo / "docs" / "kb")
    reasons.extend(f"lint: {problem}" for problem in problems)
    if run_tests:
        result = subprocess.run(
            ["python3", "-m", "unittest", "discover", "-s", "tests", "-b"],
            cwd=base_repo,
            text=True,
            capture_output=True,
            check=False,
            timeout=600,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
            reasons.append("suite failed: " + " / ".join(tail))
    return GateResult(not reasons, reasons)


def kb_changes(*, root: Path | None = None) -> list[str]:
    """Paths under docs/kb/ that git sees as changed."""
    base_repo = repo_root(root)
    result = _git(["status", "--porcelain", "--", "docs/kb"], root=base_repo)
    if result.returncode != 0:
        return []
    return [line[3:].strip() for line in result.stdout.splitlines() if line.strip()]


def commit_message(slugs: list[str], *, root: Path | None = None) -> str:
    """A message built from the entries themselves, so it says what was learned."""
    base = (repo_root(root)) / "docs" / "kb"
    lines: list[str] = []
    if len(slugs) == 1:
        entry = find_entry(slugs[0], root=base)
        verb = "Document" if entry.state == "errors" else "File"
        where = "a verified fix" if entry.state == "errors" else "an open case"
        lines.append(f"{verb} {where}: {entry.title or entry.slug}")
        lines.append("")
        lines.append(entry.tldr)
        lines.append("")
        lines.append(f"Area: {entry.area}. Slug names the symptom, not the cause.")
        if entry.state == "errors":
            lines.append(
                f"Verified {entry.meta.get('verified', '?')} by {entry.meta.get('verified_by', '?')}."
            )
        else:
            lines.append("No fix yet, so it stays in backlog/ until one is verified.")
        signatures = [s for s in entry.signatures if s.mechanical]
        if signatures:
            lines.append("")
            lines.append("Matchable signatures, so `kb match` finds this from a log:")
            for signature in signatures:
                lines.append(f"  {signature.source}: {signature.pattern}")
    else:
        lines.append(f"Update the knowledge base ({len(slugs)} entries)")
        lines.append("")
        for slug in slugs:
            try:
                entry = find_entry(slug, root=base)
            except kb.KbError:
                continue
            lines.append(f"- {entry.state}/{entry.area}/{entry.slug}: {entry.title or ''}".rstrip())
    return "\n".join(lines).rstrip() + "\n"


def commit(
    slugs: list[str],
    *,
    root: Path | None = None,
    run_tests: bool = True,
    message: str | None = None,
) -> tuple[bool, str]:
    """Stage docs/kb/ and commit, refusing on a gate failure. (ok, detail)."""
    base_repo = repo_root(root)
    verdict = gate(root=base_repo, run_tests=run_tests)
    if not verdict.ok:
        return False, "refusing to commit:\n  " + "\n  ".join(verdict.reasons)
    if not kb_changes(root=base_repo):
        return False, "nothing under docs/kb/ has changed"
    staged = _git(["add", "--", "docs/kb"], root=base_repo)
    if staged.returncode != 0:
        return False, f"git add failed: {staged.stderr.strip()}"
    text = message or commit_message(slugs, root=base_repo)
    # `-F -` reads the message from stdin, so it never reaches argv. _git is not used
    # here because it pins stdin to DEVNULL.
    result = subprocess.run(
        ["git", "commit", "-q", "-F", "-"],
        cwd=base_repo,
        input=text,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    if result.returncode != 0:
        return False, f"git commit failed: {(result.stderr or result.stdout).strip()}"
    head = _git(["log", "--format=%h %s", "-1"], root=base_repo)
    return True, head.stdout.strip()


# --- push, or a pull request ------------------------------------------------------


def can_push(*, root: Path | None = None) -> tuple[bool, str]:
    """Probe whether these credentials may push to origin, without pushing.

    `git push --dry-run` authenticates and computes the update but writes nothing, so it
    answers the question honestly. Probing the *capability* rather than comparing a
    username is what makes the contributor path work for anyone: the repository owner
    gets a direct push, everybody else is routed to a pull request, and neither is
    hardcoded.
    """
    base_repo = repo_root(root)
    result = _git(["push", "--dry-run", "origin", "HEAD:refs/heads/main"], root=base_repo, timeout=90)
    if result.returncode == 0:
        return True, "origin accepts a direct push"
    detail = (result.stderr or result.stdout).strip().splitlines()
    reason = detail[-1] if detail else f"exit {result.returncode}"
    return False, reason


def push_or_pr(*, root: Path | None = None, slug: str = "") -> tuple[str, str]:
    """Push to main if allowed, else prepare a branch and print PR instructions.

    Returns (action, detail) where action is 'pushed', 'branch' or 'blocked'.
    """
    base_repo = repo_root(root)
    allowed, reason = can_push(root=base_repo)
    if allowed:
        result = _git(["push", "origin", "HEAD:refs/heads/main"], root=base_repo, timeout=120)
        if result.returncode == 0:
            return "pushed", "pushed to origin/main"
        return "blocked", (result.stderr or result.stdout).strip()

    branch = f"kb/{slug}" if slug else "kb/update"
    current = _git(["rev-parse", "--abbrev-ref", "HEAD"], root=base_repo).stdout.strip()
    if current != branch:
        made = _git(["checkout", "-q", "-b", branch], root=base_repo)
        if made.returncode != 0:
            return "blocked", f"could not create branch {branch}: {made.stderr.strip()}"
    instructions = (
        f"no push access to origin ({reason}).\n"
        f"  Your work is committed and now on branch '{branch}'. To contribute it:\n"
        f"    gh repo fork --remote --remote-name fork   # once\n"
        f"    git push fork {branch}\n"
        f"    gh pr create --base main --head {branch} --fill\n"
        f"  Or push the branch to your own fork and open the PR in the web UI.\n"
        f"  Note: '{current}' still points at this commit too. Once the PR is open you can\n"
        f"  tidy that with: git checkout {current} && git reset --hard origin/{current}"
    )
    return "branch", instructions
