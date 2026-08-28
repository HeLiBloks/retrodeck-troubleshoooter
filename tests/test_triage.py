"""The triage rules: what counts as benign, and what a level means.

A checker whose exit code fires on normal states is worth nothing, so the rules that
suppress a false alarm are as much worth pinning as the ones that raise a real one.
"""

import unittest
from pathlib import Path

from support import ProbeTestCase, sandbox, write

from rdtroubleshoot import emulation, osquery, scraping
from rdtroubleshoot.probe import Check, Report, exit_code, render


class ExitContractTest(ProbeTestCase):
    def test_only_fail_and_warn_move_the_exit_code(self):
        self.assertEqual(exit_code([Check("PASS", "a", ""), Check("INFO", "b", "")]), 0)
        self.assertEqual(exit_code([Check("WARN", "a", ""), Check("PASS", "b", "")]), 1)
        self.assertEqual(exit_code([Check("WARN", "a", ""), Check("FAIL", "b", "")]), 2)

    def test_an_info_only_report_exits_zero(self):
        """A machine with nothing installed is not a failing machine."""
        self.assertEqual(exit_code([Check("INFO", "x", "") for _ in range(10)]), 0)

    def test_quiet_output_drops_pass_and_info(self):
        report = Report("g", [Check("PASS", "fine", "d"), Check("FAIL", "broken", "d")])
        text = render([report], colour=False, quiet=True)
        self.assertIn("broken", text)
        self.assertNotIn("fine", text)

    def test_an_unknown_level_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            Check("BROKEN", "x", "y")


class BenignDenialTest(ProbeTestCase):
    def test_the_sshd_control_socket_denial_is_filtered(self):
        """It fires on every SSH connection and has nothing to do with emulation."""
        self.assertTrue(osquery._is_benign("sshd-session", "sock_file", "system_u:object_r:ssh_home_t:s0"))

    def test_the_filter_is_narrow_enough_to_keep_a_real_denial(self):
        """A different comm, class or context must survive - the filter is a triple."""
        self.assertFalse(osquery._is_benign("retroarch", "sock_file", "system_u:object_r:ssh_home_t:s0"))
        self.assertFalse(osquery._is_benign("sshd-session", "file", "system_u:object_r:ssh_home_t:s0"))
        self.assertFalse(
            osquery._is_benign("sshd-session", "sock_file", "unconfined_u:object_r:user_home_t:s0")
        )

    def test_the_avc_regex_reads_a_real_journal_line(self):
        line = (
            'AVC avc:  denied  { create } for  pid=7352 comm="sshd-session" '
            'name="s.<random>.sshd.<random>" scontext=system_u:system_r:sshd_session_t:s0-s0:c0.c1023 '
            "tcontext=system_u:object_r:ssh_home_t:s0 tclass=sock_file permissive=0"
        )
        match = osquery._AVC_RE.search(line)
        self.assertIsNotNone(match)
        self.assertEqual(match["comm"], "sshd-session")
        self.assertEqual(match["tclass"], "sock_file")
        self.assertEqual(match["perms"].strip(), "create")

    def test_pseudo_filesystems_are_skipped_so_a_full_composefs_is_not_a_fault(self):
        """`/` is a 45 MB composefs at 100% used on every ostree host, for ever."""
        self.assertIn("composefs", osquery.PSEUDO_FSTYPES)
        self.assertIn("overlay", osquery.PSEUDO_FSTYPES)
        self.assertIn("tmpfs", osquery.PSEUDO_FSTYPES)


class LogNoiseTest(ProbeTestCase):
    def test_mesa_glthread_at_error_severity_is_noise(self):
        """Ryujinx logs it at |E| and Mesa is not even driving the game here."""
        line = (
            "|E| ATTENTION: default value of option mesa_glthread overridden by environment"
        )
        self.assertTrue(emulation.ERROR_LINE_RE.search(line))
        self.assertTrue(emulation.LOG_NOISE_RE.search(line), "must be filtered out")

    def test_a_real_error_line_is_not_filtered(self):
        line = "|E| Application CheckLaunchState: Couldn't find any application in '...nsp'."
        self.assertTrue(emulation.ERROR_LINE_RE.search(line))
        self.assertFalse(emulation.LOG_NOISE_RE.search(line))

    def test_the_pgrep_pattern_is_bracketed(self):
        """Unbracketed, pgrep matches its own command line and always reports running."""
        pattern = emulation._bracketed_pattern()
        self.assertEqual(pattern, "[e]s-de|[e]mulationstation|[n]et.retrodeck")
        for term in emulation.RETRODECK_PROCESS_TERMS:
            self.assertNotIn(term, pattern, f"{term} must be broken up by brackets")


class SwitchUpdateTest(ProbeTestCase):
    """Title ids below are synthetic - the shape is what the rule reads, not the game."""

    BASE = "Some Game [0100000000001000][v0].nsp"
    UPDATE = "Some Game [0100000000001800][v131072].nsp"

    def test_an_update_nsp_is_recognised_by_its_title_id(self):
        self.assertTrue(emulation.UPDATE_NSP_RE.search(self.UPDATE))

    def test_a_base_game_is_not(self):
        self.assertIsNone(emulation.UPDATE_NSP_RE.search(self.BASE))

    def test_the_rule_reads_the_id_and_not_the_version_field(self):
        """`[v131072]` also contains digits; only the 16-hex title id may decide."""
        self.assertIsNone(
            emulation.UPDATE_NSP_RE.search("Some Game [0100000000001000][v800].nsp")
        )

    def test_a_bare_filename_with_no_title_id_is_not_an_update(self):
        self.assertIsNone(emulation.UPDATE_NSP_RE.search("Some Game.nsp"))


class QuotaMarkerTest(ProbeTestCase):
    def test_the_markers_are_full_sentences(self):
        """Short substrings both missed two messages and matched game descriptions.

        'Get a bigger quota!' appears in real prose, so 'quota' alone false-positives.
        """
        for marker in scraping.QUOTA_MARKERS:
            self.assertGreater(len(marker.split()), 3, f"{marker!r} is too short to be safe")

    def test_a_game_description_mentioning_quota_does_not_match(self):
        prose = "shoot the aliens and get a bigger quota! now with more levels".lower()
        self.assertFalse(any(marker in prose for marker in scraping.QUOTA_MARKERS))

    def test_the_real_closure_message_matches(self):
        text = "the screenscraper api is currently closed or too busy, please retry later"
        self.assertTrue(any(marker in text for marker in scraping.QUOTA_MARKERS))


class BackupRotationTest(ProbeTestCase):
    def test_only_digit_suffixed_backups_belong_to_the_rotation(self):
        """A hand-labelled checkpoint is one the rotation may not delete.

        Counting those made the parent project's check WARN permanently while the
        rotation was working exactly as specified.
        """
        self.assertTrue(scraping.ROTATED_BACKUP_RE.match("gamelist.xml.bak.20260824203234"))
        self.assertIsNone(scraping.ROTATED_BACKUP_RE.match("gamelist.xml.bak.before-prune"))
        self.assertIsNone(scraping.ROTATED_BACKUP_RE.match("gamelist.xml.bak.keep-me"))

    def test_labelled_backups_are_reported_but_do_not_trip_the_warning(self):
        with sandbox() as root:
            system = root / "retrodeck/ES-DE/gamelists/amiga"
            write(system / "gamelist.xml", "<gameList/>")
            for index in range(30):
                write(system / f"gamelist.xml.bak.keep{index}", "x")
            check = scraping._backups()
            self.assertEqual(check.level, "PASS", "30 hand-labelled files are not a rotation fault")

    def test_too_many_rotated_backups_do_trip_it(self):
        with sandbox() as root:
            system = root / "retrodeck/ES-DE/gamelists/amiga"
            write(system / "gamelist.xml", "<gameList/>")
            for index in range(20):
                write(system / f"gamelist.xml.bak.2026082420{index:04d}", "x")
            check = scraping._backups()
            self.assertEqual(check.level, "WARN")


if __name__ == "__main__":
    unittest.main()


class PermissiveDenialTest(ProbeTestCase):
    """A denial in a permissive domain blocked nothing, so it is not a fault.

    Bazzite ships `bootupd_t` permissive, and it denies `lsblk` a read on /proc/swaps at
    every boot. Reporting that as three warnings is three warnings about a boot that
    worked. This is a general rule, which is why it beats adding lsblk to a benign list.
    """

    PERMISSIVE = (
        'AVC avc:  denied  { open } for  pid=1427 comm="lsblk" path="/proc/swaps" '
        "dev=\"proc\" ino=4026532100 scontext=system_u:system_r:bootupd_t:s0 "
        "tcontext=system_u:object_r:proc_t:s0 tclass=file permissive=1"
    )
    ENFORCED = (
        'AVC avc:  denied  { create } for  pid=7352 comm="retroarch" name="x" '
        "scontext=system_u:system_r:unconfined_t:s0 "
        "tcontext=unconfined_u:object_r:user_home_t:s0 tclass=sock_file permissive=0"
    )

    def test_the_permissive_flag_is_captured(self):
        match = osquery._AVC_RE.search(self.PERMISSIVE)
        self.assertIsNotNone(match)
        self.assertEqual(match["permissive"], "1")
        self.assertEqual(match["comm"], "lsblk")

    def test_an_enforced_denial_is_captured_as_such(self):
        match = osquery._AVC_RE.search(self.ENFORCED)
        self.assertIsNotNone(match)
        self.assertEqual(match["permissive"], "0")

    def test_a_line_without_the_field_still_parses(self):
        """The regex must not require permissive=, which not every kernel emits."""
        line = self.ENFORCED.replace(" permissive=0", "")
        match = osquery._AVC_RE.search(line)
        self.assertIsNotNone(match)
        self.assertIsNone(match["permissive"])


class CoverageNoiseTest(ProbeTestCase):
    def test_a_tiny_folder_with_gaps_does_not_warn(self):
        """Six WARNs for nine missing tags is what teaches a user to ignore the exit code."""
        with sandbox() as root:
            base = root / "retrodeck/ES-DE/gamelists"
            write(base / "quake/gamelist.xml", "<gameList><game><path>./q.pk3</path></game></gameList>")
            checks = scraping._coverage()
            self.assertFalse(
                [c for c in checks if c.level == "WARN"],
                "a one-entry folder must not raise a warning",
            )
            self.assertTrue([c for c in checks if "small folders" in c.name])

    def test_a_real_folder_with_a_real_gap_does_warn(self):
        with sandbox() as root:
            entries = "".join(
                f"<game><path>./g{index}.zip</path></game>" for index in range(20)
            )
            write(root / "retrodeck/ES-DE/gamelists/amiga/gamelist.xml", f"<gameList>{entries}</gameList>")
            checks = scraping._coverage()
            self.assertTrue(
                [c for c in checks if c.level == "WARN" and "amiga" in c.name],
                "20 entries with no descriptions is a genuine coverage gap",
            )


class TwoLogFormatsTest(ProbeTestCase):
    """One file interleaves two log formats, and the scan must read both.

    Reading only Ryujinx's `|E|` reported "no real |E| lines" on a real log holding 124
    `[WARN]` and one `[ERROR]` — a false clean, which is the worst thing a checker can say.
    """

    ESDE_ERROR = (
        "[2026-08-27 20:06:01.996] [ERROR] [ES-DE] setReportingLevelFromRetroDeckConfig: "
        "Failed to read rd_logging_level - RETRODECK_CONFIG_HOME environment variable not set."
    )
    ESDE_WARN = (
        '[2026-08-27 20:06:02.100] [WARN] [ES-DE] File "/roms/naomi/cvs2/gdl-0007a.chd" is '
        "present in gamelist.xml but the extension is not configured in es_systems.xml"
    )
    RYUJINX_ERROR = "00:00:11 |E| Application CheckLaunchState: Couldn't find any application"
    RYUJINX_WARN = "00:00:12 |W| Hid Remap: No matching controllers found."

    def test_both_error_formats_are_recognised(self):
        self.assertTrue(emulation.ERROR_LINE_RE.search(self.ESDE_ERROR))
        self.assertTrue(emulation.ERROR_LINE_RE.search(self.RYUJINX_ERROR))

    def test_both_warning_formats_are_recognised(self):
        self.assertTrue(emulation.WARN_LINE_RE.search(self.ESDE_WARN))
        self.assertTrue(emulation.WARN_LINE_RE.search(self.RYUJINX_WARN))

    def test_an_info_line_is_not_read_as_either(self):
        info = "[2026-08-27 20:08:30.829] [INFO] [ES-DE] Launching game \"X\" from system \"n64\""
        self.assertIsNone(emulation.ERROR_LINE_RE.search(info))
        self.assertIsNone(emulation.WARN_LINE_RE.search(info))

    def test_a_debug_line_is_not_read_as_either(self):
        """8430 of one real log's 8678 lines are DEBUG; reading them as findings is useless."""
        debug = "[2026-08-27 20:06:02.001] [DEBUG] [ES-DE] FileData::FileData(): whatever"
        self.assertIsNone(emulation.ERROR_LINE_RE.search(debug))
        self.assertIsNone(emulation.WARN_LINE_RE.search(debug))

    def test_the_dead_entry_class_is_recognised_from_both_of_its_lines(self):
        """ES-DE logs twice per unopenable entry; both must route to one finding."""
        self.assertTrue(emulation.DEAD_ENTRY_RE.search(self.ESDE_WARN))
        self.assertTrue(
            emulation.DEAD_ENTRY_RE.search(
                '[WARN] [ES-DE] Couldn\'t process "/roms/naomi/cvs2/gdl-0007a.chd", skipping entry'
            )
        )

    def test_normalise_keeps_the_front_of_the_line(self):
        """The informative half of an error is its start; a tail slice truncated '[ERROR]'."""
        key = emulation._normalise(self.ESDE_ERROR)
        self.assertTrue(key.startswith("[ERROR]"), key[:40])
        self.assertNotIn("2026-08-27", key)

    def test_normalise_collapses_quoted_paths_so_a_class_groups(self):
        one = emulation._normalise('[WARN] [ES-DE] File "/a/b.chd" is present in gamelist.xml')
        two = emulation._normalise('[WARN] [ES-DE] File "/c/d.chd" is present in gamelist.xml')
        self.assertEqual(one, two)

    def test_mesa_noise_is_still_filtered_in_the_ryujinx_format(self):
        line = "|E| ATTENTION: default value of option mesa_glthread overridden by environment"
        self.assertTrue(emulation.ERROR_LINE_RE.search(line))
        self.assertTrue(emulation.LOG_NOISE_RE.search(line))

    def test_a_missing_file_warning_is_parsed_for_its_path(self):
        line = '[WARN] [ES-DE] File "/roms/neogeo/jonasindiana.zip" does not exist, skipping entry'
        match = emulation.MISSING_FILE_RE.search(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(2), "/roms/neogeo/jonasindiana.zip")

    def test_a_known_benign_error_is_info_not_warn(self):
        """Warning on a known-normal line is how an exit code stops being read.

        The mirror mistake is dropping it silently, which is how a checker goes blind. So
        it is reported, with the reason, at INFO — the same treatment the benign SELinux
        denials get.
        """
        line = (
            "[ERROR] [ES-DE] setReportingLevelFromRetroDeckConfig: Failed to read "
            "rd_logging_level - RETRODECK_CONFIG_HOME environment variable not set."
        )
        self.assertTrue(
            any(pattern.search(line) for pattern, _ in emulation.BENIGN_ERRORS),
            "the RetroDECK logging-level fallback must be recognised as benign",
        )

    def test_the_benign_list_is_narrow_enough_to_keep_a_real_error(self):
        real = "[ERROR] [ES-DE] Couldn't open gamelist.xml for writing"
        self.assertFalse(any(pattern.search(real) for pattern, _ in emulation.BENIGN_ERRORS))

    def test_every_benign_entry_carries_an_explanation(self):
        """An unexplained suppression is indistinguishable from a bug."""
        for pattern, why in emulation.BENIGN_ERRORS:
            self.assertGreater(len(why.split()), 5, f"{pattern.pattern} has no real explanation")
