"""Stdlib only, read from the AST rather than by importing.

The parent project's one violation hid all three of its imports inside function bodies,
which is why this walks the tree instead of trusting a top-of-file scan - an import inside
a function is still an import, and it fails at the worst possible moment: after a run has
staged its work and before it reports.
"""

from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOCAL_MODULES = {"support", "rdtroubleshoot"}


def _python_files() -> list[Path]:
    files = sorted((REPO / "src").rglob("*.py"))
    files += sorted((REPO / "tests").rglob("*.py"))
    # rglob, not glob: tools/ may grow subdirectories, and a non-recursive sweep is how
    # the parent project's tools/verify/ went unchecked while its docs told both agents
    # to run it.
    files += sorted((REPO / "tools").rglob("*.py"))
    files += [REPO / "rdtroubleshoot"]
    return [path for path in files if path.is_file()]


def _top_level_imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import is our own package
                continue
            if node.module:
                names.add(node.module.split(".")[0])
    return names


class StdlibOnlyTest(unittest.TestCase):
    def test_every_import_is_stdlib_or_local(self):
        stdlib = set(sys.stdlib_module_names)
        offenders: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(), filename=str(path))
            for name in sorted(_top_level_imports(tree)):
                if name in stdlib or name in LOCAL_MODULES:
                    continue
                offenders.append(f"{path.relative_to(REPO)}: {name}")
        self.assertEqual(offenders, [], "third-party imports found")

    def test_the_sweep_actually_covers_the_tree(self):
        """A guard that cannot fire is worse than none.

        The parent project's version of this used a non-recursive glob over tools/, so a
        subdirectory its own docs told both agents to run was never checked.
        """
        swept = {path.relative_to(REPO).as_posix() for path in _python_files()}
        for expected in (
            "src/rdtroubleshoot/cli.py",
            "src/rdtroubleshoot/osquery.py",
            "src/rdtroubleshoot/inputs.py",
            "rdtroubleshoot",
            "tests/test_stdlib_only.py",
        ):
            self.assertIn(expected, swept, f"{expected} is not being checked")

    def test_pyproject_declares_no_dependencies(self):
        text = (REPO / "pyproject.toml").read_text()
        # A tomllib parse would be tidier, but the assertion is about the literal file:
        # a commented-out or oddly-quoted dependency list still installs nothing, and a
        # non-empty one must fail loudly however it is spelled.
        import tomllib

        data = tomllib.loads(text)
        self.assertEqual(data["project"].get("dependencies", []), [])
        self.assertEqual(data["project"].get("optional-dependencies", {}), {})


if __name__ == "__main__":
    unittest.main()
