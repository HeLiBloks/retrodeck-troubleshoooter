"""Half-set credentials, which are worse than none, and never printing the secret."""

import unittest

from support import ProbeTestCase, sandbox, write

from rdtroubleshoot import scraping


def config(text: str, root):
    return write(root / ".skyscraper/config.ini", text)


class CredentialTest(ProbeTestCase):
    def test_a_missing_password_is_a_failure_not_a_warning(self):
        """`userCreds="user:"` sends an empty password on every request.

        Login is refused, the run scrapes nothing, and repeated bad logins carry a
        blacklist risk. It once cost a silent 4-5 hour nohup'd run, so it is FAIL.
        """
        with sandbox() as root:
            config('[screenscraper]\nuserCreds="exampleuser:"\n', root)
            checks = scraping._credentials()
            creds = [check for check in checks if check.name == "ScreenScraper creds"]
            self.assertEqual(creds[0].level, "FAIL")
            self.assertIn("password", creds[0].detail)

    def test_a_missing_username_fails_too(self):
        with sandbox() as root:
            config('userCreds=":secret"\n', root)
            creds = [c for c in scraping._credentials() if c.name == "ScreenScraper creds"]
            self.assertEqual(creds[0].level, "FAIL")
            self.assertIn("username", creds[0].detail)

    def test_the_password_is_never_printed(self):
        """Not the value, and not its length either."""
        secret = "hunter2correcthorse"
        with sandbox() as root:
            config(f'userCreds="exampleuser:{secret}"\n', root)
            for check in scraping._credentials():
                self.assertNotIn(secret, check.detail + check.fix)
                self.assertNotIn(str(len(secret)), check.detail)

    def test_hazardous_password_characters_are_warned_about(self):
        """Skyscraper builds the query string raw; ';' can act as a param separator."""
        with sandbox() as root:
            config('userCreds="user:has$dollar;semi"\n', root)
            creds = [c for c in scraping._credentials() if c.name == "ScreenScraper creds"]
            self.assertEqual(creds[0].level, "WARN")
            self.assertIn("$", creds[0].detail)
            self.assertNotIn("has$dollar;semi", creds[0].detail)

    def test_a_good_credential_passes_and_names_only_the_user(self):
        with sandbox() as root:
            config('userCreds="exampleuser:alphanumeric123"\n', root)
            creds = [c for c in scraping._credentials() if c.name == "ScreenScraper creds"]
            self.assertEqual(creds[0].level, "PASS")
            self.assertIn("exampleuser", creds[0].detail)

    def test_no_config_is_information_not_a_fault(self):
        with sandbox():
            creds = [c for c in scraping._credentials() if c.name == "ScreenScraper creds"]
            self.assertEqual(creds[0].level, "INFO")

    def test_a_group_readable_config_is_flagged(self):
        with sandbox() as root:
            path = config('userCreds="user:pass"\n', root)
            path.chmod(0o644)
            perms = [c for c in scraping._credentials() if c.name == "config.ini permissions"]
            self.assertEqual(len(perms), 1)
            self.assertEqual(perms[0].level, "WARN")

    def test_an_owner_only_config_is_not_flagged(self):
        with sandbox() as root:
            path = config('userCreds="user:pass"\n', root)
            path.chmod(0o600)
            self.assertFalse([c for c in scraping._credentials() if c.name == "config.ini permissions"])


if __name__ == "__main__":
    unittest.main()
