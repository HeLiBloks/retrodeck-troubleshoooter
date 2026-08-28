"""The knowledge base: the frontmatter subset, matching, and the promotion gate.

Most of these are about the gate. It is the only thing standing between "we think this
works" and somebody else acting on it, so every rule it enforces is pinned here — and each
was checked by removing the rule and watching this file fail.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from support import ProbeTestCase, sandbox, write

from rdtroubleshoot import kb, kb_ops

GOOD_ERROR = """---
slug: demo-symptom
area: input
status: fixed
first_seen: 2026-08-01
last_confirmed: 2026-08-02
verified: 2026-08-02
verified_by: the game drew its title screen
signatures:
  - source: retrodeck-log
    pattern: Hid Remap: No matching controllers found
    note: repeats every two seconds
  - source: symptom
    pattern: black screen
---

# A demo symptom

## TL;DR

Do the thing.

---

## Engineer notes

### Symptom signature

```
Hid Remap: No matching controllers found
```
"""

GOOD_BACKLOG = GOOD_ERROR.replace("status: fixed", "status: open").replace(
    "verified: 2026-08-02\nverified_by: the game drew its title screen\n", ""
)


def make_kb(root: Path) -> Path:
    """A minimal but lint-clean KB tree."""
    base = root / "docs" / "kb"
    for state in ("errors", "backlog"):
        for area in kb.AREAS:
            (base / state / area).mkdir(parents=True, exist_ok=True)
        write(base / state / "INDEX.md", "# Index\n\n| Keyword | Entry |\n| --- | --- |\n")
    (base / "evals").mkdir(parents=True, exist_ok=True)
    write(base / "errors" / "_template.md", GOOD_ERROR)
    write(base / "backlog" / "_template.md", GOOD_BACKLOG)
    return base


def add_row(base: Path, state: str, area: str, slug: str) -> None:
    path = kb.index_path(base, state)
    path.write_text(path.read_text() + f"| something | [{slug}]({area}/{slug}.md) |\n")


class FrontmatterTest(ProbeTestCase):
    def test_a_pattern_containing_a_colon_survives(self):
        """`Hid Remap: No matching controllers found` is a real signature.

        Splitting on every colon instead of the first would truncate it to 'Hid Remap',
        which still matches — silently, and far too broadly.
        """
        meta, _ = kb.parse_frontmatter(GOOD_ERROR)
        self.assertEqual(
            meta["signatures"][0]["pattern"], "Hid Remap: No matching controllers found"
        )

    def test_the_body_is_returned_intact(self):
        _, body = kb.parse_frontmatter(GOOD_ERROR)
        self.assertTrue(body.lstrip().startswith("# A demo symptom"))
        self.assertIn("## TL;DR", body)

    def test_quotes_are_stripped_but_inner_ones_are_kept(self):
        meta, _ = kb.parse_frontmatter('---\na: "x: y"\nb: \'z\'\n---\nbody\n')
        self.assertEqual(meta["a"], "x: y")
        self.assertEqual(meta["b"], "z")

    def test_missing_frontmatter_raises_rather_than_returning_empty(self):
        """A silently-ignored frontmatter is an entry with no signatures that nobody notices."""
        with self.assertRaises(kb.KbError):
            kb.parse_frontmatter("# just a heading\n")

    def test_unclosed_frontmatter_raises(self):
        with self.assertRaises(kb.KbError):
            kb.parse_frontmatter("---\nslug: x\n")

    def test_nesting_beyond_the_documented_subset_raises(self):
        """Better to refuse than to drop a key the author believed was read."""
        text = "---\nslug: x\nnested:\n  deeper:\n    value: 1\n---\nbody\n"
        with self.assertRaises(kb.KbError):
            kb.parse_frontmatter(text)


class MatchingTest(ProbeTestCase):
    def test_a_log_line_routes_to_its_entry(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            entries = kb.load_all(base)
            matches = kb.match_text(
                entries,
                "00:01 |W| Hid Remap: No matching controllers found.\n",
                source="retrodeck-log",
            )
            self.assertEqual([m.entry.slug for m in matches], ["demo-symptom"])

    def test_a_symptom_signature_is_never_matched_mechanically(self):
        """`symptom` is prose for a human; matching it against a log invites nonsense."""
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            entries = kb.load_all(base)
            self.assertFalse(kb.match_text(entries, "black screen", source="symptom"))

    def test_a_signature_only_matches_its_own_source(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            entries = kb.load_all(base)
            self.assertFalse(
                kb.match_text(entries, "Hid Remap: No matching controllers found", source="journal")
            )

    def test_a_fixed_entry_outranks_an_open_one(self):
        """A caller taking the first match must get the actionable answer."""
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            other = GOOD_BACKLOG.replace("demo-symptom", "open-symptom")
            write(base / "backlog" / "input" / "open-symptom.md", other)
            entries = kb.load_all(base)
            matches = kb.match_text(
                entries, "Hid Remap: No matching controllers found", source="retrodeck-log"
            )
            self.assertEqual(matches[0].entry.state, "errors")

    def test_load_all_returns_errors_before_backlog(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "open-symptom.md",
                  GOOD_BACKLOG.replace("demo-symptom", "open-symptom"))
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            self.assertEqual([e.state for e in kb.load_all(base)], ["errors", "backlog"])

    def test_templates_are_not_loaded_as_entries(self):
        with sandbox() as root:
            base = make_kb(root)
            self.assertEqual(kb.load_all(base), [])


class LintTest(ProbeTestCase):
    def test_a_well_formed_tree_is_clean(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            write(base / "evals" / "demo-symptom.md", "---\nslug: demo-symptom\n---\nfixture\n")
            add_row(base, "errors", "input", "demo-symptom")
            self.assertEqual(kb.lint(base), [])

    def _one_error(self, root: Path, text: str, *, state="errors", area="input", slug="demo-symptom"):
        base = make_kb(root)
        write(base / state / area / f"{slug}.md", text)
        write(base / "evals" / f"{slug}.md", "---\nslug: x\n---\nfixture\n")
        add_row(base, state, area, slug)
        return kb.lint(base)

    def test_an_errors_entry_without_verified_is_refused(self):
        """This IS the promotion gate. Without it the two states mean nothing."""
        with sandbox() as root:
            broken = GOOD_ERROR.replace("verified: 2026-08-02\n", "")
            problems = self._one_error(root, broken)
            self.assertTrue(any("promotion gate" in p for p in problems), problems)

    def test_an_errors_entry_without_verified_by_is_refused(self):
        with sandbox() as root:
            broken = GOOD_ERROR.replace("verified_by: the game drew its title screen\n", "")
            problems = self._one_error(root, broken)
            self.assertTrue(any("verified_by" in p for p in problems), problems)

    def test_a_backlog_entry_may_not_claim_verified(self):
        """If it is verified, it belongs in errors/ — claiming it here hides a fix."""
        with sandbox() as root:
            sneaky = GOOD_BACKLOG.replace(
                "last_confirmed: 2026-08-02", "last_confirmed: 2026-08-02\nverified: 2026-08-02"
            )
            problems = self._one_error(root, sneaky, state="backlog")
            self.assertTrue(any("must not claim 'verified'" in p for p in problems), problems)

    def test_an_entry_with_no_index_row_is_refused(self):
        """An entry nobody can find is worse than no entry: the work looks done."""
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            write(base / "evals" / "demo-symptom.md", "fixture")
            problems = kb.lint(base)
            self.assertTrue(any("no row in errors/INDEX.md" in p for p in problems), problems)

    def test_an_errors_entry_with_no_eval_fixture_is_refused(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            add_row(base, "errors", "input", "demo-symptom")
            problems = kb.lint(base)
            self.assertTrue(any("no evals/" in p for p in problems), problems)

    def test_an_entry_whose_every_signature_is_symptom_is_refused(self):
        """Nothing could ever route to it from a log, so it is unreachable in practice."""
        with sandbox() as root:
            prose_only = GOOD_ERROR.replace("  - source: retrodeck-log\n    pattern: Hid Remap: No matching controllers found\n    note: repeats every two seconds\n", "")
            problems = self._one_error(root, prose_only)
            self.assertTrue(any("every signature is 'symptom'" in p for p in problems), problems)

    def test_a_slug_disagreeing_with_its_filename_is_refused(self):
        with sandbox() as root:
            problems = self._one_error(root, GOOD_ERROR, slug="different-name")
            self.assertTrue(any("disagrees with the filename" in p for p in problems), problems)

    def test_an_area_disagreeing_with_its_directory_is_refused(self):
        """The area is also a checker group, so a wrong one breaks the --kb annotation."""
        with sandbox() as root:
            problems = self._one_error(root, GOOD_ERROR, area="os")
            self.assertTrue(any("disagrees with the directory" in p for p in problems), problems)

    def test_an_invalid_regex_signature_is_refused(self):
        with sandbox() as root:
            broken = GOOD_ERROR.replace("pattern: Hid Remap: No matching", "pattern: Hid Remap: [unclosed")
            problems = self._one_error(root, broken)
            self.assertTrue(any("not valid regex" in p for p in problems), problems)

    def test_a_missing_divider_is_refused(self):
        """The TL;DR and engineer halves are answered to different audiences."""
        with sandbox() as root:
            broken = GOOD_ERROR.replace("\n---\n\n## Engineer notes", "\n\n## Engineer notes")
            problems = self._one_error(root, broken)
            self.assertTrue(any("divider" in p for p in problems), problems)

    def test_a_bad_date_format_is_refused(self):
        with sandbox() as root:
            broken = GOOD_ERROR.replace("first_seen: 2026-08-01", "first_seen: last tuesday")
            problems = self._one_error(root, broken)
            self.assertTrue(any("first_seen" in p for p in problems), problems)

    def test_the_shipped_knowledge_base_is_clean(self):
        """The real docs/kb/, not a fixture — this is what `kb check` runs in anger."""
        self.assertEqual(kb.lint(), [])


class PromotionTest(ProbeTestCase):
    def test_promotion_requires_a_verified_by_record(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "demo-symptom.md", GOOD_BACKLOG)
            with self.assertRaises(kb.KbError):
                kb_ops.promote("demo-symptom", verified_by="   ", root=base)

    def test_promotion_moves_the_file_and_stamps_the_verification(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "demo-symptom.md", GOOD_BACKLOG)
            add_row(base, "backlog", "input", "demo-symptom")
            target = kb_ops.promote("demo-symptom", verified_by="the check passes", root=base)
            self.assertTrue(target.is_file())
            self.assertFalse((base / "backlog" / "input" / "demo-symptom.md").exists())
            entry = kb.load_entry(target)
            self.assertEqual(entry.status, "fixed")
            self.assertEqual(entry.meta["verified_by"], "the check passes")
            self.assertTrue(kb.DATE_RE.match(entry.meta["verified"]))

    def test_promotion_carries_the_index_row_across(self):
        """Otherwise the entry is invisible in its new home and a stale row points nowhere."""
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "demo-symptom.md", GOOD_BACKLOG)
            add_row(base, "backlog", "input", "demo-symptom")
            kb_ops.promote("demo-symptom", verified_by="observed", root=base)
            self.assertIn("demo-symptom", kb.index_path(base, "errors").read_text())
            self.assertNotIn("demo-symptom", kb.index_path(base, "backlog").read_text())

    def test_promotion_scaffolds_an_eval_fixture(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "demo-symptom.md", GOOD_BACKLOG)
            kb_ops.promote("demo-symptom", verified_by="observed", root=base)
            self.assertTrue((base / "evals" / "demo-symptom.md").is_file())

    def test_promoting_twice_is_refused(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "errors" / "input" / "demo-symptom.md", GOOD_ERROR)
            with self.assertRaises(kb.KbError):
                kb_ops.promote("demo-symptom", verified_by="observed", root=base)


class SightingTest(ProbeTestCase):
    def test_a_sighting_appends_and_moves_last_confirmed(self):
        with sandbox() as root:
            base = make_kb(root)
            write(base / "backlog" / "input" / "demo-symptom.md", GOOD_BACKLOG)
            kb_ops.add_sighting("demo-symptom", "seen again on the box", root=base)
            text = (base / "backlog" / "input" / "demo-symptom.md").read_text()
            self.assertIn("seen again on the box", text)
            self.assertIn(f"last_confirmed: {kb_ops.today()}", text)

    def test_a_sighting_on_an_unknown_slug_raises(self):
        with sandbox() as root:
            base = make_kb(root)
            with self.assertRaises(kb.KbError):
                kb_ops.add_sighting("no-such-entry", "x", root=base)


class NewEntryTest(ProbeTestCase):
    def test_a_new_entry_is_born_in_backlog(self):
        """The lifecycle in one assertion: a case starts without a fix."""
        with sandbox() as root:
            base = make_kb(root)
            path = kb_ops.new_entry(slug="fresh-case", area="os", title="Something", root=base)
            self.assertIn("backlog", path.parts)

    def test_a_bad_slug_is_refused(self):
        with sandbox() as root:
            base = make_kb(root)
            for bad in ("Fresh_Case", "fresh case", "FRESH", "fresh--"):
                with self.assertRaises(kb.KbError, msg=bad):
                    kb_ops.new_entry(slug=bad, area="os", title="x", root=base)

    def test_an_unknown_area_is_refused(self):
        with sandbox() as root:
            base = make_kb(root)
            with self.assertRaises(kb.KbError):
                kb_ops.new_entry(slug="fresh-case", area="graphics", title="x", root=base)

    def test_creating_over_an_existing_entry_is_refused(self):
        with sandbox() as root:
            base = make_kb(root)
            kb_ops.new_entry(slug="fresh-case", area="os", title="x", root=base)
            with self.assertRaises(kb.KbError):
                kb_ops.new_entry(slug="fresh-case", area="os", title="x", root=base)


class AreaCouplingTest(ProbeTestCase):
    def test_every_kb_area_is_a_checker_group(self):
        """The coupling that makes --kb work. Breaking it silently disables the annotation."""
        from rdtroubleshoot.cli import GROUPS

        for area in kb.AREAS:
            self.assertIn(area, GROUPS, f"KB area {area!r} is not a checker group")

    def test_the_checker_source_is_available_for_signatures(self):
        self.assertIn("checker", kb.SOURCES)
        self.assertIn("checker", kb.MECHANICAL_SOURCES)


if __name__ == "__main__":
    unittest.main()
