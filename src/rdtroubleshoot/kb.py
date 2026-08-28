"""The knowledge base: entries, their machine-matchable signatures, and the lint.

The structure is lifted from a support-desk repo that has been through ~60 entries, and
the parts that survived contact are the parts worth copying:

- **Two states, not one.** `backlog/` is a case with no fix yet; `errors/` is a case with a
  verified fix. Promotion happens only when the cause *and* a user-actionable fix are
  verified, never on a hunch. The one-sentence test: if you can tell the user what to
  *do*, it is an `errors/` entry; if all you can honestly say is "seen it, no fix yet", it
  is a `backlog/` entry.
- **The slug names the dominant symptom, not the cause.** Causes get re-diagnosed;
  symptoms are what someone greps for a year later.
- **Single sightings are welcome.** Filing a one-off precisely is the only thing that makes
  a *second* sighting recognisable as a pattern.
- **An entry with no INDEX row is invisible.** So the lint fails on it, rather than trusting
  whoever adds the next entry to remember.

What is new here, and the reason this is not just a folder of prose: an entry's signatures
are **machine-matchable**, so `kb match` can grep a live log against the whole KB. The
source repo matched by having a model read its index; this repo already owns a log reader,
so the KB may as well be executable. That is also what lets the commit gate be enforced
instead of promised - `verified_by` names a check whose output can be re-run.

Frontmatter is a deliberately restricted YAML subset: top-level scalars, plus top-level
keys holding a list of flat mappings. No nesting beyond that, no multi-line scalars. The
project is stdlib-only, so a full YAML parser is not available; rather than pretend, the
subset is documented and `kb check` fails on anything outside it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# Areas are exactly the checker's group names, so a failing check can name its area's
# entries and an entry can name the check that verifies it. Do not add an area without a
# corresponding group - the coupling is the point.
AREAS = ("os", "flatpak", "emulation", "input", "scraping")

# Where a signature can be matched. `symptom` is prose for a human and is never matched
# mechanically; everything else names something readable on disk or a check name.
SOURCES = (
    "retrodeck-log",     # ~/.var/app/net.retrodeck.retrodeck/.../retrodeck.log
    "bios-log",          # retrodeck_bios_check.log
    "journal",           # systemd journal
    "ryujinx-config",    # Ryujinx Config.json
    "gamelist",          # any ES-DE gamelist.xml
    "checker",           # an rdtroubleshoot check name, e.g. "Ryujinx input match"
    "symptom",           # human description; never matched mechanically
)
MECHANICAL_SOURCES = tuple(s for s in SOURCES if s != "symptom")

STATUSES = ("open", "fixed")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# The divider between the two halves of an entry. The TL;DR half is what a user is told;
# the engineer half is crossed into only on request.
DIVIDER = "\n---\n"
REQUIRED_SECTIONS = ("## TL;DR", "## Engineer notes", "### Symptom signature")


class KbError(Exception):
    """A malformed entry. Carries a message naming the file and the problem."""


# --- the restricted frontmatter parser --------------------------------------------


def _scalar(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def parse_frontmatter(text: str, *, where: str = "<string>") -> tuple[dict, str]:
    """Split `---`-delimited frontmatter from the body.

    Returns (mapping, body). Raises KbError for anything outside the documented subset,
    because a silently-ignored key is a signature that never matches and nobody notices.
    """
    if not text.startswith("---\n"):
        raise KbError(f"{where}: no frontmatter (the file must start with '---')")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise KbError(f"{where}: frontmatter is not closed by a '---' line")
    head, body = text[4:end], text[end + 5 :]

    data: dict = {}
    current_list: list[dict] | None = None
    current_item: dict | None = None
    for number, line in enumerate(head.splitlines(), start=2):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0:
            if ":" not in stripped:
                raise KbError(f"{where}:{number}: expected 'key: value'")
            key, _, value = stripped.partition(":")
            key = key.strip()
            if value.strip() == "":
                current_list = []
                current_item = None
                data[key] = current_list
            else:
                current_list = None
                current_item = None
                data[key] = _scalar(value)
            continue

        if stripped.startswith("- "):
            if current_list is None:
                raise KbError(f"{where}:{number}: list item outside a list key")
            key, _, value = stripped[2:].partition(":")
            if not _:
                raise KbError(f"{where}:{number}: expected 'key: value' in a list item")
            current_item = {key.strip(): _scalar(value)}
            current_list.append(current_item)
            continue

        # A continuation key belonging to the current list item.
        if current_item is None:
            raise KbError(
                f"{where}:{number}: indented line with no list item to attach to "
                "(nested mappings are not supported - see the frontmatter subset)"
            )
        key, _, value = stripped.partition(":")
        if not _:
            raise KbError(f"{where}:{number}: expected 'key: value'")
        current_item[key.strip()] = _scalar(value)
    return data, body


# --- the entry model --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Signature:
    source: str
    pattern: str
    note: str = ""

    @property
    def mechanical(self) -> bool:
        return self.source in MECHANICAL_SOURCES

    def compiled(self) -> re.Pattern[str]:
        return re.compile(self.pattern, re.IGNORECASE)


@dataclass
class Entry:
    path: Path
    slug: str
    area: str
    status: str
    title: str
    body: str
    meta: dict = field(default_factory=dict)
    signatures: list[Signature] = field(default_factory=list)

    @property
    def state(self) -> str:
        """'errors' or 'backlog', taken from the path rather than the frontmatter.

        The directory is the authority: a file's location is what the promotion step
        actually changes, so trusting a `status:` field that could disagree with it would
        let a fixed entry sit in backlog for ever.
        """
        parts = self.path.parts
        return "errors" if "errors" in parts else "backlog"

    @property
    def tldr(self) -> str:
        after = self.body.split("## TL;DR", 1)
        if len(after) < 2:
            return ""
        return after[1].split(DIVIDER, 1)[0].strip()

    def rel(self, root: Path) -> str:
        return self.path.relative_to(root).as_posix()


def kb_root(start: Path | None = None) -> Path:
    return (start or Path(__file__).resolve().parents[2]) / "docs" / "kb"


def load_entry(path: Path) -> Entry:
    text = path.read_text(errors="replace")
    where = path.name
    meta, body = parse_frontmatter(text, where=where)
    title = ""
    for line in body.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    signatures = [
        Signature(
            source=item.get("source", ""),
            pattern=item.get("pattern", ""),
            note=item.get("note", ""),
        )
        for item in meta.get("signatures", [])
        if isinstance(item, dict)
    ]
    return Entry(
        path=path,
        slug=str(meta.get("slug", "")),
        area=str(meta.get("area", "")),
        status=str(meta.get("status", "")),
        title=title,
        body=body,
        meta=meta,
        signatures=signatures,
    )


def load_all(root: Path | None = None) -> list[Entry]:
    """Every entry under errors/ and backlog/, errors first.

    Order matters and is the same rule the source repo uses: a fixed entry outranks an
    open one, so a caller taking the first match gets the actionable answer.
    """
    base = root or kb_root()
    entries: list[Entry] = []
    for state in ("errors", "backlog"):
        folder = base / state
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.md")):
            if path.name.startswith("_") or path.name == "INDEX.md":
                continue
            entries.append(load_entry(path))
    return entries


# --- matching ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Match:
    entry: Entry
    signature: Signature
    line: str
    count: int


def match_text(entries: list[Entry], text: str, *, source: str) -> list[Match]:
    """Every entry whose signature for `source` appears in `text`, best first.

    Ranked by state (a fixed entry before an open one), then by how many of the entry's
    signatures hit — an entry matching two independent signatures is a better answer than
    one matching a single generic line.

    **A `symptom` signature is never matched here**, whatever `source` is asked for. It is
    prose written for a human ("black screen after the game loads"), so matching it against
    a log routes every file containing those words to the entry. The CLI also restricts
    `--source`, but the invariant belongs at this level: a caller passing `source="symptom"`
    gets nothing rather than nonsense. Prose is searched by `search()` instead.
    """
    if source not in MECHANICAL_SOURCES:
        return []
    lines = text.splitlines()
    found: list[Match] = []
    for entry in entries:
        for signature in entry.signatures:
            if signature.source != source or not signature.pattern:
                continue
            if not signature.mechanical:
                continue
            try:
                pattern = signature.compiled()
            except re.error:
                continue
            hits = [line for line in lines if pattern.search(line)]
            if hits:
                found.append(Match(entry, signature, hits[-1].strip(), len(hits)))
    per_entry: dict[str, int] = {}
    for item in found:
        per_entry[item.entry.slug] = per_entry.get(item.entry.slug, 0) + 1
    found.sort(key=lambda m: (m.entry.state != "errors", -per_entry[m.entry.slug], -m.count))
    return found


def search(entries: list[Entry], term: str) -> list[Entry]:
    """Entries whose slug, title, signatures or TL;DR mention `term`. Errors first."""
    needle = term.lower()
    hits = [
        entry
        for entry in entries
        if needle in entry.slug.lower()
        or needle in entry.title.lower()
        or needle in entry.tldr.lower()
        or any(needle in s.pattern.lower() or needle in s.note.lower() for s in entry.signatures)
    ]
    hits.sort(key=lambda e: (e.state != "errors", e.slug))
    return hits


# --- the lint ---------------------------------------------------------------------


def index_path(root: Path, state: str) -> Path:
    return root / state / "INDEX.md"


def index_slugs(root: Path, state: str) -> set[str]:
    """Slugs an INDEX table routes to. A row links to the entry; the stem is the slug."""
    path = index_path(root, state)
    if not path.is_file():
        return set()
    text = path.read_text(errors="replace")
    return {Path(target).stem for target in re.findall(r"\]\(([^)]+\.md)\)", text)}


def lint(root: Path | None = None) -> list[str]:
    """Every problem found, as human-readable strings. Empty means clean.

    This is what `kb check` reports and what the commit gate refuses on. Each rule below
    stands for a way a knowledge base rots: an entry nobody can find, a fix nobody
    verified, a signature that cannot compile, a slug that disagrees with its filename.
    """
    base = root or kb_root()
    problems: list[str] = []
    if not base.is_dir():
        return [f"{base} does not exist"]

    seen: dict[str, Path] = {}
    for state in ("errors", "backlog"):
        folder = base / state
        if not folder.is_dir():
            problems.append(f"missing directory {folder}")
            continue
        indexed = index_slugs(base, state)
        for path in sorted(folder.rglob("*.md")):
            if path.name.startswith("_") or path.name == "INDEX.md":
                continue
            rel = path.relative_to(base).as_posix()
            try:
                entry = load_entry(path)
            except KbError as error:
                problems.append(str(error))
                continue

            if not SLUG_RE.match(entry.slug):
                problems.append(f"{rel}: slug {entry.slug!r} is not lower-kebab-case")
            if entry.slug != path.stem:
                problems.append(f"{rel}: slug {entry.slug!r} disagrees with the filename")
            if entry.slug in seen:
                problems.append(f"{rel}: duplicate slug, also in {seen[entry.slug]}")
            seen[entry.slug] = Path(rel)

            if entry.area not in AREAS:
                problems.append(f"{rel}: area {entry.area!r} is not one of {', '.join(AREAS)}")
            elif path.parent.name != entry.area:
                problems.append(
                    f"{rel}: area {entry.area!r} disagrees with the directory {path.parent.name!r}"
                )
            if entry.status not in STATUSES:
                problems.append(f"{rel}: status {entry.status!r} is not open|fixed")
            if not entry.title:
                problems.append(f"{rel}: no '# ' title line")

            for key in ("first_seen", "last_confirmed"):
                value = entry.meta.get(key)
                if not value:
                    problems.append(f"{rel}: missing {key}")
                elif not DATE_RE.match(str(value)):
                    problems.append(f"{rel}: {key} {value!r} is not YYYY-MM-DD")

            # The promotion gate, enforced rather than promised.
            if state == "errors":
                if entry.status != "fixed":
                    problems.append(f"{rel}: an errors/ entry must have status: fixed")
                verified = entry.meta.get("verified")
                if not verified or not DATE_RE.match(str(verified)):
                    problems.append(
                        f"{rel}: an errors/ entry needs a 'verified: YYYY-MM-DD' date - "
                        "that field IS the promotion gate"
                    )
                if not entry.meta.get("verified_by"):
                    problems.append(
                        f"{rel}: an errors/ entry needs 'verified_by' naming how the fix was "
                        "confirmed (a check name, a command, or an observation)"
                    )
            else:
                if entry.status != "open":
                    problems.append(
                        f"{rel}: a backlog/ entry must have status: open "
                        "(promote it into errors/ instead)"
                    )
                if entry.meta.get("verified"):
                    problems.append(
                        f"{rel}: a backlog/ entry must not claim 'verified' - if the fix is "
                        "verified, promote it"
                    )

            if DIVIDER not in entry.body:
                problems.append(f"{rel}: no '---' divider between the TL;DR and engineer halves")
            for section in REQUIRED_SECTIONS:
                if section not in entry.body:
                    problems.append(f"{rel}: missing section {section!r}")
            if not entry.tldr:
                problems.append(f"{rel}: the TL;DR is empty")

            if not entry.signatures:
                problems.append(f"{rel}: no signatures - nothing can ever match this entry")
            for signature in entry.signatures:
                if signature.source not in SOURCES:
                    problems.append(
                        f"{rel}: signature source {signature.source!r} is not one of "
                        f"{', '.join(SOURCES)}"
                    )
                if not signature.pattern:
                    problems.append(f"{rel}: a signature has no pattern")
                    continue
                try:
                    signature.compiled()
                except re.error as error:
                    problems.append(f"{rel}: signature pattern is not valid regex: {error}")
            if not any(s.mechanical for s in entry.signatures):
                problems.append(
                    f"{rel}: every signature is 'symptom' - add at least one matchable "
                    "source so `kb match` can find this from a log"
                )

            if entry.slug not in indexed:
                problems.append(
                    f"{rel}: no row in {state}/INDEX.md - an entry with no INDEX row is "
                    "invisible to anyone searching"
                )

    # An eval fixture is the regression record for a promoted entry.
    for path in sorted((base / "errors").rglob("*.md")):
        if path.name.startswith("_") or path.name == "INDEX.md":
            continue
        fixture = base / "evals" / f"{path.stem}.md"
        if not fixture.is_file():
            problems.append(
                f"errors/{path.parent.name}/{path.name}: no evals/{path.stem}.md fixture - "
                "promotion must record the case that proved the fix"
            )
    return problems
