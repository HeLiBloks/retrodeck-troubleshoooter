"""Where RetroDECK keeps things, and the one path trap that matters.

`$HOME` on Bazzite is `/home/retro`, a symlink to `/var/home/retro`. Both spellings
reach the same directory and they are **not** interchangeable in a gamelist: ES-DE and
Skyscraper match old entries to new ones by the raw `<path>` string, so a file written
under one spelling loses every entry written under the other. Generating `model2` with
the resolved spelling once cost 7 of 59 descriptions and 22 playcount tags.

So nothing here resolves a path. `same_directory()` exists for the one question that
does need resolution - "are these two spellings the same place?" - and is used only to
detect the mismatch, never to rewrite anything.
"""

from __future__ import annotations

import os
from pathlib import Path

from .probe import home

RETRODECK_APP_ID = "net.retrodeck.retrodeck"
RYUJINX_APP_ID = "io.github.ryubing.Ryujinx"
SUPERMODEL_APP_ID = "com.supermodel3.Supermodel"


def retrodeck_root() -> Path:
    return Path(os.environ.get("RETRODECK_HOME") or home() / "retrodeck")


def roms_dir() -> Path:
    return Path(os.environ.get("RETRODECK_ROMS") or retrodeck_root() / "roms")


def esde_dir() -> Path:
    return Path(os.environ.get("RETRODECK_ESDE") or retrodeck_root() / "ES-DE")


def gamelists_dir() -> Path:
    return esde_dir() / "gamelists"


def media_dir() -> Path:
    return esde_dir() / "downloaded_media"


def bios_dir() -> Path:
    return retrodeck_root() / "bios"


def app_config(app_id: str) -> Path:
    return home() / ".var" / "app" / app_id / "config"


def retrodeck_logs() -> Path:
    return app_config(RETRODECK_APP_ID) / "retrodeck" / "logs"


def retrodeck_log() -> Path:
    return retrodeck_logs() / "retrodeck.log"


def bios_log() -> Path:
    return retrodeck_logs() / "retrodeck_bios_check.log"


def esde_settings() -> Path:
    return app_config(RETRODECK_APP_ID) / "ES-DE" / "settings" / "es_settings.xml"


def ryujinx_config() -> Path:
    return app_config(RYUJINX_APP_ID) / "Ryujinx" / "Config.json"


def skyscraper_home() -> Path:
    return home() / ".skyscraper"


def same_directory(left: Path, right: Path) -> bool:
    """True when two different spellings name one directory.

    Compares device+inode rather than realpath text, so a bind mount counts as the same
    place and a missing path is simply not equal to anything.
    """
    try:
        a, b = left.stat(), right.stat()
    except OSError:
        return False
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def spelling_variants(path: Path) -> list[Path]:
    """The other ways this machine spells `path`, e.g. /home/... vs /var/home/...

    Returns only spellings that exist and land on the same directory.
    """
    text = str(path)
    candidates: list[str] = []
    if text.startswith("/var/home/"):
        candidates.append("/home/" + text[len("/var/home/") :])
    elif text.startswith("/home/"):
        candidates.append("/var/home/" + text[len("/home/") :])
    return [Path(c) for c in candidates if same_directory(Path(c), path)]
