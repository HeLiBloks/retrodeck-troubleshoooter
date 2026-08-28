"""The two-root gamelist, which every plain XML parser refuses."""

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from support import GAMELIST, GAMELIST_WITH_SIBLING, ProbeTestCase, sandbox, write

from rdtroubleshoot import gamelist as gl


class GamelistTest(ProbeTestCase):
    def test_plain_gamelist_takes_the_happy_path(self):
        with sandbox() as root:
            path = write(root / "gamelist.xml", GAMELIST)
            parsed = gl.read(path)
            self.assertFalse(parsed.siblings, "a normal file must not go through the text fallback")
            self.assertEqual(len(parsed.games), 2)

    def test_esde_sibling_root_is_parsed_not_refused(self):
        """`<alternativeEmulator>` beside `<gameList>` is two roots, so ET refuses it.

        ES-DE writes it and accepts it. A checker that calls this file corrupt reports a
        fault on a perfectly working system.
        """
        with sandbox() as root:
            path = write(root / "gamelist.xml", GAMELIST_WITH_SIBLING)
            with self.assertRaises(ET.ParseError):
                ET.parse(path)  # the behaviour we are working around
            parsed = gl.read(path)
            self.assertTrue(parsed.siblings)
            self.assertEqual(len(parsed.games), 1)
            self.assertEqual(parsed.games[0].findtext("name"), "Zool")

    def test_a_file_broken_some_other_way_still_raises(self):
        """Turning a corrupt gamelist into a quietly truncated one is the worst outcome."""
        with sandbox() as root:
            path = write(root / "gamelist.xml", "<gameList><game><path>x</path>")
            with self.assertRaises(ET.ParseError):
                gl.read(path)

    def test_paths_are_read_by_regex_over_the_whole_file(self):
        """Not via the parser, and not only the first block.

        The scraper's version of this once read 64 KB, so a gamelist whose absolute
        entries all sat past ~100 games reported no mismatch at all.
        """
        with sandbox() as root:
            filler = "\n".join(
                f"  <game><path>./filler{index}.zip</path></game>" for index in range(4000)
            )
            path = write(
                root / "gamelist.xml",
                f"<?xml version='1.0'?>\n<gameList>\n{filler}\n"
                "  <game><path>/var/home/retro/retrodeck/roms/amiga/Late.zip</path></game>\n"
                "</gameList>\n",
            )
            self.assertGreater(path.stat().st_size, 100_000)
            found = gl.paths_in(path)
            self.assertIn("/var/home/retro/retrodeck/roms/amiga/Late.zip", found)

    def test_tag_counts_only_count_non_empty(self):
        with sandbox() as root:
            path = write(root / "gamelist.xml", GAMELIST)
            counts = gl.tag_counts(gl.read(path), ("desc", "genre"))
            self.assertEqual(counts["desc"], 1, "the empty <desc> must not count")
            self.assertEqual(counts["genre"], 1)


if __name__ == "__main__":
    unittest.main()
