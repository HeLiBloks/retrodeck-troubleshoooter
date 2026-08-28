"""Sandbox reachability. Getting this wrong means telling a user their sandbox is fine."""

import os
import unittest
from pathlib import Path

from support import ProbeTestCase, sandbox

from rdtroubleshoot.flatpakq import access_to, parse_grant


def grants(*entries: str):
    return [parse_grant(entry) for entry in entries]


class GrantParsingTest(ProbeTestCase):
    def test_host_covers_everything_and_is_writable(self):
        grant = parse_grant("host")
        self.assertEqual(grant.path, Path("/"))
        self.assertTrue(grant.writable)

    def test_ro_suffix_is_not_writable(self):
        self.assertFalse(parse_grant("home:ro").writable)
        self.assertTrue(parse_grant("home").writable)
        self.assertTrue(parse_grant("home:create").writable)

    def test_home_resolves_to_the_unresolved_home(self):
        with sandbox() as root:
            self.assertEqual(parse_grant("home").path, root)

    def test_xdg_tokens_expand(self):
        with sandbox() as root:
            self.assertEqual(parse_grant("xdg-config/MangoHud:create").path, root / ".config/MangoHud")
            self.assertEqual(parse_grant("xdg-data/Steam").path, root / ".local/share/Steam")

    def test_an_absolute_grant_is_taken_literally(self):
        self.assertEqual(parse_grant("/run/udev:ro").path, Path("/run/udev"))


class AccessTest(ProbeTestCase):
    def test_home_covers_a_rom_tree_inside_home(self):
        with sandbox() as root:
            roms = root / "retrodeck/roms"
            self.assertIsNotNone(access_to(grants("home"), roms))

    def test_ro_home_is_found_but_not_writable(self):
        """Ryujinx's real grant here. It can load a ROM and cannot write a save beside it."""
        with sandbox() as root:
            grant = access_to(grants("home:ro", "xdg-pictures"), root / "retrodeck/roms")
            self.assertIsNotNone(grant)
            self.assertFalse(grant.writable)

    def test_a_rom_tree_outside_home_is_not_covered_by_home(self):
        """The case that presents as an empty system in the carousel."""
        with sandbox():
            self.assertIsNone(access_to(grants("home", "xdg-pictures"), Path("/mnt/roms")))

    def test_an_unrelated_specific_grant_does_not_cover_a_sibling(self):
        with sandbox() as root:
            self.assertIsNone(access_to(grants("~/Documents"), root / "retrodeck/roms"))

    def test_a_writable_grant_wins_over_a_read_only_one(self):
        with sandbox() as root:
            roms = root / "retrodeck/roms"
            grant = access_to(grants("home:ro", "host"), roms)
            self.assertTrue(grant.writable, "the broadest writable grant must be reported")

    def test_empty_entries_are_ignored_not_treated_as_root(self):
        """A trailing ';' in filesystems= yields an empty entry; it must cover nothing."""
        self.assertIsNone(parse_grant("").path)
        with sandbox() as root:
            self.assertIsNone(access_to(grants(""), root / "retrodeck/roms"))


if __name__ == "__main__":
    unittest.main()
