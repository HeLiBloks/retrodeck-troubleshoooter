"""Reading a gamelist without tripping over the two things that break parsers.

**A gamelist can have two root elements.** When a per-system emulator override is set,
ES-DE writes `<alternativeEmulator><label>...</label></alternativeEmulator>` as a
*sibling* of `<gameList>`. ES-DE's own parser accepts that; two roots is not well-formed
XML, so `ElementTree` refuses the whole file with "junk after document element". In the
scraper this presented as `[<system>] enrichment failed` for one folder, on every run,
for as long as the override was set - and in a checker it presents as a corrupt-gamelist
alarm on a file ES-DE is perfectly happy with.

**A file broken some other way must still look broken.** If no `<gameList>` can be
found, the original error is re-raised rather than swallowed - turning a corrupt gamelist
into a quietly truncated one is the worst outcome available here.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_GAMELIST_RE = re.compile(rb"<gameList\b.*?</gameList\s*>", re.DOTALL | re.IGNORECASE)
_DECL_RE = re.compile(rb"^\s*<\?xml[^>]*\?>", re.DOTALL)


@dataclass(frozen=True, slots=True)
class Gamelist:
    path: Path
    root: ET.Element
    siblings: bool  # a second root element (ES-DE's alternativeEmulator) was present

    @property
    def games(self) -> list[ET.Element]:
        return list(self.root.findall("game"))


def read(path: Path) -> Gamelist:
    """Parse a gamelist, tolerating ES-DE's sibling root element.

    Raises ET.ParseError for a file that is genuinely malformed, and OSError when it
    cannot be read.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as first_error:
        data = path.read_bytes()
        match = _GAMELIST_RE.search(data)
        if match is None:
            raise first_error
        # Re-parse the located element on its own, so a truncated file still raises
        # rather than silently becoming a shorter gamelist.
        return Gamelist(path, ET.fromstring(match.group(0)), siblings=True)
    return Gamelist(path, tree.getroot(), siblings=False)


def paths_in(path: Path) -> list[str]:
    """Every `<path>` value, by regex over the whole file.

    Deliberately not via the parser: an unparseable gamelist is exactly the one whose
    paths still need checking, and the scraper's version of this once read only the first
    64 KB and so reported no mismatch for any file whose absolute entries sat past ~100
    games.
    """
    try:
        data = path.read_text(errors="replace")
    except OSError:
        return []
    return re.findall(r"<path>([^<]*)</path>", data)


def tag_counts(gamelist: Gamelist, tags: tuple[str, ...]) -> dict[str, int]:
    """How many entries carry a non-empty value for each tag.

    Counting these separately is the point: a folder can read 98% described and still be
    45% un-genred, which is how mame looked before the filename bridge ran.
    """
    counts = dict.fromkeys(tags, 0)
    for game in gamelist.games:
        for tag in tags:
            element = game.find(tag)
            if element is not None and (element.text or "").strip():
                counts[tag] += 1
    return counts
