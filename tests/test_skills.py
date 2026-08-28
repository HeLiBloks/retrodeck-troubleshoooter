"""The skill list in CLAUDE.md is the discovery mechanism for Codex, so it may not drift.

Claude Code scans `.claude/skills/`. Codex reads only the root `AGENTS.md`, which here is
CLAUDE.md through a symlink. A skill that exists on disk but is not listed is therefore
invisible to half the agents working in this repository.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / ".claude" / "skills"


def skill_dirs() -> list[Path]:
    return sorted(path for path in SKILLS.iterdir() if path.is_dir())


class SkillTest(unittest.TestCase):
    def test_agents_md_is_the_same_bytes_as_claude_md(self):
        agents = REPO / "AGENTS.md"
        self.assertTrue(agents.is_symlink(), "AGENTS.md must be a symlink, not a copy that can drift")
        self.assertEqual(agents.resolve(), (REPO / "CLAUDE.md").resolve())

    def test_every_skill_is_listed_in_claude_md(self):
        listed = (REPO / "CLAUDE.md").read_text()
        for path in skill_dirs():
            self.assertIn(
                f"skills/{path.name}/SKILL.md",
                listed,
                f"skill '{path.name}' exists but is not listed in CLAUDE.md, so Codex cannot see it",
            )

    def test_every_skill_has_a_skill_md_with_name_and_description(self):
        for path in skill_dirs():
            skill = path / "SKILL.md"
            self.assertTrue(skill.is_file(), f"{path.name} has no SKILL.md")
            text = skill.read_text()
            self.assertTrue(text.startswith("---\n"), f"{path.name}: no frontmatter")
            frontmatter = text.split("---", 2)[1]
            self.assertRegex(frontmatter, r"(?m)^name:\s*\S+", f"{path.name}: no name in frontmatter")
            self.assertRegex(frontmatter, r"(?m)^description:\s*\S+", f"{path.name}: no description")

    def test_the_frontmatter_name_matches_the_directory(self):
        for path in skill_dirs():
            frontmatter = (path / "SKILL.md").read_text().split("---", 2)[1]
            name = re.search(r"(?m)^name:\s*(\S+)", frontmatter).group(1)
            self.assertEqual(name, path.name, f"{path.name}: frontmatter name disagrees with the directory")

    def test_every_skill_carries_an_agents_md_symlink(self):
        """Read by Codex when it is invoked from inside that directory."""
        for path in skill_dirs():
            agents = path / "AGENTS.md"
            self.assertTrue(agents.is_symlink(), f"{path.name}: AGENTS.md is not a symlink")
            self.assertEqual(agents.resolve(), (path / "SKILL.md").resolve())

    def test_skill_links_into_docs_resolve(self):
        """A skill that points at a doc which does not exist is worse than one that does not."""
        for path in skill_dirs():
            text = (path / "SKILL.md").read_text()
            for target in re.findall(r"\]\((\.\./[^)]+)\)", text):
                resolved = (path / target).resolve()
                self.assertTrue(resolved.exists(), f"{path.name}: broken link to {target}")


if __name__ == "__main__":
    unittest.main()
