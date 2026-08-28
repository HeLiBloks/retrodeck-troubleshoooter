"""Shared fixtures. Nothing here touches the network or a real RetroDECK tree."""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@contextlib.contextmanager
def sandbox(**env: str):
    """A temp dir as $HOME, with the RetroDECK env vars pointed inside it.

    Pinning HOME matters: without it a check that globs the real home passes or fails
    for reasons that have nothing to do with the test.
    """
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        saved = {key: os.environ.get(key) for key in ("HOME", "RETRODECK_HOME", "RETRODECK_ROMS", "RETRODECK_ESDE", *env)}
        os.environ["HOME"] = str(root)
        os.environ["RETRODECK_HOME"] = str(root / "retrodeck")
        os.environ.pop("RETRODECK_ROMS", None)
        os.environ.pop("RETRODECK_ESDE", None)
        os.environ.update(env)
        try:
            yield root
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


GAMELIST = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Zool.zip</path>
    <name>Zool</name>
    <desc>A ninja from another dimension.</desc>
    <genre>Platform</genre>
  </game>
  <game>
    <path>./Turrican.zip</path>
    <name>Turrican</name>
    <desc></desc>
  </game>
</gameList>
"""

# ES-DE writes this second root element when a per-system emulator override is set.
GAMELIST_WITH_SIBLING = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Zool.zip</path>
    <name>Zool</name>
    <desc>A ninja from another dimension.</desc>
    <genre>Platform</genre>
  </game>
</gameList>
<alternativeEmulator>
  <label>PUAE 2021 (Standalone)</label>
</alternativeEmulator>
"""


class ProbeTestCase(unittest.TestCase):
    pass
