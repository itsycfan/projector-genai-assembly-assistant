"""Configuration loading, path resolution and secret handling.

Settings are read from ``config/config.ini`` (copy it from
``config/config.example.ini``). Secrets such as API keys and passwords are
never stored in the configuration file. They are read from environment
variables, optionally loaded from a local ``.env`` file.
"""

from __future__ import annotations

import configparser
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.ini"

try:  # Optional: load secrets from a local .env file (git-ignored).
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:  # pragma: no cover
    pass


class Config:
    """Thin wrapper around :class:`configparser.ConfigParser`."""

    def __init__(self, path: str | Path | None = None):
        env_path = os.environ.get("PGA_CONFIG")
        self.file_path = Path(path or env_path or DEFAULT_CONFIG_PATH)
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.file_path}\n"
                "Copy config/config.example.ini to config/config.ini and adjust it."
            )

        self._parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
        with open(self.file_path, encoding="utf-8") as f:
            self._parser.read_file(f)

        base_dir = Path(self._parser.get("Paths", "BASE_DIR", fallback="."))
        self.base_dir = base_dir if base_dir.is_absolute() else (REPO_ROOT / base_dir).resolve()

    # Typed accessors -------------------------------------------------------
    def get(self, section: str, key: str, fallback: str | None = None) -> str | None:
        return self._parser.get(section, key, fallback=fallback)

    def getint(self, section: str, key: str, fallback: int | None = None) -> int | None:
        return self._parser.getint(section, key, fallback=fallback)

    def getfloat(self, section: str, key: str, fallback: float | None = None) -> float | None:
        return self._parser.getfloat(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback: bool | None = None) -> bool | None:
        return self._parser.getboolean(section, key, fallback=fallback)

    def path(self, key: str, create: bool = False) -> Path:
        """Resolve a ``[Paths]`` entry relative to ``BASE_DIR``.

        If ``create`` is true, the directory is created when missing.
        """
        value = Path(self._parser.get("Paths", key))
        resolved = value if value.is_absolute() else self.base_dir / value
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        return resolved


def get_secret(name: str) -> str:
    """Return a secret from the environment or raise a helpful error."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Environment variable {name} is not set. "
            f"Export it in your shell or add it to a local .env file."
        )
    return value
