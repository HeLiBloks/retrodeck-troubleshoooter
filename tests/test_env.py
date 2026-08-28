"""The .env loader. Most of these are about what must NOT happen to a secret."""

from __future__ import annotations

import os
import stat
import unittest
from pathlib import Path

from support import ProbeTestCase, sandbox, write

from rdtroubleshoot import env

SECRET = "sup3r-s3cret-root-pw"


def env_file(root: Path, text: str, mode: int = 0o600) -> Path:
    path = write(root / ".env", text)
    path.chmod(mode)
    return path


class ParsingTest(ProbeTestCase):
    def test_it_tolerates_what_people_actually_write(self):
        values = env.parse(
            "\n".join(
                [
                    "# a comment",
                    "",
                    "RDT_SSH_TARGET=retro@box",
                    "export RDT_ROMS=/mnt/roms",
                    "SS_USER = spaced",
                    'SS_PASS="quoted value"',
                    "RDT_ESDE='single'",
                ]
            )
        )
        self.assertEqual(values["RDT_SSH_TARGET"], "retro@box")
        self.assertEqual(values["RDT_ROMS"], "/mnt/roms", "export prefix must be accepted")
        self.assertEqual(values["SS_USER"], "spaced", "spaces around = must be accepted")
        self.assertEqual(values["SS_PASS"], "quoted value")
        self.assertEqual(values["RDT_ESDE"], "single")

    def test_an_embedded_quote_is_preserved(self):
        """Only one surrounding pair is stripped; a password may legitimately contain them."""
        self.assertEqual(env.parse('SS_PASS="he said ""hi"""')["SS_PASS"], 'he said ""hi""')

    def test_an_unquoted_trailing_comment_is_not_part_of_the_value(self):
        self.assertEqual(env.parse("SS_USER=bob  # the account")["SS_USER"], "bob")

    def test_a_quoted_hash_is_part_of_the_value(self):
        """A '#' is a perfectly ordinary password character."""
        self.assertEqual(env.parse('SS_PASS="pa#ss"')["SS_PASS"], "pa#ss")

    def test_comments_and_blank_lines_yield_nothing(self):
        self.assertEqual(env.parse("# only a comment\n\n   \n"), {})


class SecrecyTest(ProbeTestCase):
    def test_the_repr_does_not_contain_the_secret(self):
        """The default dataclass repr would put the password into any traceback."""
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n")
            creds = env.load(root / ".env")
            self.assertNotIn(SECRET, repr(creds))
            self.assertNotIn(SECRET, str(creds))

    def test_redacted_never_reveals_a_secret_value(self):
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\nSS_PASS={SECRET}\nSS_USER=bob\n")
            creds = env.load(root / ".env")
            redacted = creds.redacted()
            self.assertEqual(redacted["RDT_SUDO_PASSWORD"], "<set>")
            self.assertEqual(redacted["SS_PASS"], "<set>")
            self.assertEqual(redacted["SS_USER"], "bob", "a non-secret stays readable")
            self.assertNotIn(SECRET, str(redacted))

    def test_no_check_line_contains_the_secret(self):
        """Every string this module hands the reporter must be safe to print."""
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n")
            creds = env.load(root / ".env")
            for check in env.collect_checks(creds):
                self.assertNotIn(SECRET, check.detail + check.fix + check.name)

    def test_no_check_line_leaks_the_secret_when_the_mode_is_bad(self):
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n", mode=0o644)
            creds = env.load(root / ".env")
            for check in env.collect_checks(creds):
                self.assertNotIn(SECRET, check.detail + check.fix)


class InsecureModeTest(ProbeTestCase):
    def test_a_world_readable_env_withholds_its_secrets(self):
        """Using the password would tell the user everything is fine.

        It is not fine: a root password sits in a file anyone on the box can read. So the
        finding is raised AND the secret is refused, rather than warning and proceeding.
        """
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\nSS_USER=bob\n", mode=0o644)
            creds = env.load(root / ".env")
            self.assertIsNotNone(creds.insecure_mode)
            self.assertIsNone(creds.get("RDT_SUDO_PASSWORD"), "the secret must be withheld")
            self.assertFalse(creds.can_sudo)
            self.assertEqual(creds.get("SS_USER"), "bob", "a non-secret is still usable")

    def test_that_withholding_is_reported_as_a_failure(self):
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n", mode=0o640)
            checks = env.collect_checks(env.load(root / ".env"))
            self.assertEqual([c.level for c in checks if c.name == ".env permissions"], ["FAIL"])

    def test_an_owner_only_env_is_usable(self):
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n", mode=0o600)
            creds = env.load(root / ".env")
            self.assertIsNone(creds.insecure_mode)
            self.assertTrue(creds.can_sudo)

    def test_sudo_run_refuses_when_the_secret_is_withheld(self):
        """The gate must hold at the point of use, not only at the report."""
        with sandbox() as root:
            env_file(root, f"RDT_SUDO_PASSWORD={SECRET}\n", mode=0o644)
            self.assertIsNone(env.sudo_run(["true"], env.load(root / ".env")))


class AbsenceTest(ProbeTestCase):
    def test_no_env_file_is_not_a_fault(self):
        with sandbox() as root:
            creds = env.load(root / "nope.env")
            self.assertIsNone(creds.path)
            self.assertFalse(creds.can_sudo)
            checks = env.collect_checks(creds)
            self.assertTrue(all(check.level == "INFO" for check in checks))

    def test_an_empty_value_counts_as_unset(self):
        """The template ships RDT_SUDO_PASSWORD= with no value; that must not read as set."""
        with sandbox() as root:
            env_file(root, "RDT_SUDO_PASSWORD=\nSS_USER=bob\n")
            creds = env.load(root / ".env")
            self.assertFalse(creds.can_sudo)
            self.assertEqual(creds.get("SS_USER"), "bob")

    def test_unrecognised_keys_are_noted_and_ignored(self):
        with sandbox() as root:
            env_file(root, "SOMETHING_ELSE=1\nSS_USER=bob\n")
            creds = env.load(root / ".env")
            self.assertEqual(creds.get("SS_USER"), "bob")
            self.assertTrue(any("SOMETHING_ELSE" in note for note in creds.notes))


class PathOverrideTest(ProbeTestCase):
    def test_a_real_environment_variable_wins_over_the_env_file(self):
        """Precedence is flag > environment > .env, so a one-off override still works."""
        with sandbox() as root:
            env_file(root, "RDT_ROMS=/from/dotenv\n")
            os.environ["RETRODECK_ROMS"] = "/from/environ"
            try:
                env.apply_paths(env.load(root / ".env"))
                self.assertEqual(os.environ["RETRODECK_ROMS"], "/from/environ")
            finally:
                os.environ.pop("RETRODECK_ROMS", None)

    def test_the_env_file_fills_an_unset_variable(self):
        with sandbox() as root:
            env_file(root, "RDT_ROMS=/from/dotenv\n")
            os.environ.pop("RETRODECK_ROMS", None)
            try:
                env.apply_paths(env.load(root / ".env"))
                self.assertEqual(os.environ["RETRODECK_ROMS"], "/from/dotenv")
            finally:
                os.environ.pop("RETRODECK_ROMS", None)


class TemplateTest(ProbeTestCase):
    def test_the_shipped_template_parses_and_sets_no_secret(self):
        """The template must be copyable as-is without accidentally enabling anything."""
        template = Path(__file__).resolve().parents[1] / ".env_template"
        self.assertTrue(template.is_file(), ".env_template must be tracked")
        values = env.parse(template.read_text())
        self.assertEqual(values.get("RDT_SUDO_PASSWORD", ""), "", "the template must ship no password")
        self.assertEqual(values.get("SS_PASS", ""), "")
        for key in values:
            self.assertIn(key, env.KNOWN_KEYS, f"template documents unknown key {key}")

    def test_every_known_key_is_documented_in_the_template(self):
        """A key the code reads and the template omits is one nobody will ever set."""
        template = (Path(__file__).resolve().parents[1] / ".env_template").read_text()
        for key in env.KNOWN_KEYS:
            self.assertIn(key, template, f"{key} is not mentioned in .env_template")

    def test_dot_env_is_gitignored(self):
        ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text()
        self.assertIn("\n.env\n", ignore, ".env must never be committable")


if __name__ == "__main__":
    unittest.main()
