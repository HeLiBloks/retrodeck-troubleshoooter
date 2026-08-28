"""The /home vs /var/home spelling, and the rule that nothing here resolves a path."""

import os
import unittest
from pathlib import Path

from support import ProbeTestCase, sandbox

from rdtroubleshoot import paths


class PathTest(ProbeTestCase):
    def test_home_is_taken_from_the_environment_unresolved(self):
        """Resolving is exactly what cost the parent project 7 descriptions.

        `$HOME` on Bazzite is /home/retro, a symlink to /var/home/retro. ES-DE and
        Skyscraper match gamelist entries by the raw <path> string, so the spelling is
        load-bearing and must survive untouched.
        """
        with sandbox() as root:
            link = root / "link-home"
            real = root / "real-home"
            real.mkdir()
            link.symlink_to(real)
            os.environ["HOME"] = str(link)
            self.assertEqual(paths.home(), link, "home() must not resolve the symlink")

    def test_spelling_variants_finds_the_other_spelling_only_when_it_is_the_same_place(self):
        with sandbox() as root:
            real = root / "var" / "home" / "someone"
            real.mkdir(parents=True)
            # Not the /home <-> /var/home pair, so there is nothing to report.
            self.assertEqual(paths.spelling_variants(real), [])

    def test_same_directory_compares_identity_not_text(self):
        with sandbox() as root:
            real = root / "real"
            real.mkdir()
            link = root / "link"
            link.symlink_to(real)
            self.assertTrue(paths.same_directory(link, real))
            self.assertFalse(paths.same_directory(root / "missing", real))

    def test_env_vars_override_the_defaults(self):
        with sandbox() as root:
            os.environ["RETRODECK_ROMS"] = "/mnt/games"
            try:
                self.assertEqual(paths.roms_dir(), Path("/mnt/games"))
            finally:
                os.environ.pop("RETRODECK_ROMS", None)

    def test_the_defaults_hang_off_retrodeck_home(self):
        with sandbox() as root:
            self.assertEqual(paths.roms_dir(), root / "retrodeck" / "roms")
            self.assertEqual(paths.gamelists_dir(), root / "retrodeck" / "ES-DE" / "gamelists")


if __name__ == "__main__":
    unittest.main()
