"""
Configuration loader for piply-opdf.

Loads YAML configuration and merges with defaults.
Provides a singleton Config object used by all phases.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Path to the bundled default config
_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """
    Unified configuration object.

    Loads the bundled default.yaml, then optionally merges a user-supplied
    YAML file on top of it.

    Usage
    -----
    >>> cfg = Config()                         # defaults only
    >>> cfg = Config("my_config.yaml")        # custom overrides
    >>> cfg.get("ocr.engine")                 # dot-notation access
    >>> cfg["assessment"]["blur_threshold"]    # dict-style access
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        self._data: dict[str, Any] = self._load_defaults()

        if config_path is not None:
            user_data = self._load_yaml(Path(config_path))
            self._data = _deep_merge(self._data, user_data)
            logger.debug("Merged user config from %s", config_path)

    # ── loading ──────────────────────────────────────────────────────────────

    def _load_defaults(self) -> dict[str, Any]:
        if _DEFAULT_CONFIG_PATH.exists():
            return self._load_yaml(_DEFAULT_CONFIG_PATH)
        logger.warning("Default config not found at %s — using empty config", _DEFAULT_CONFIG_PATH)
        return {}

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data or {}

    # ── access ───────────────────────────────────────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """
        Dot-notation key lookup.

        Example
        -------
        >>> cfg.get("assessment.blur_threshold", 100.0)
        """
        parts = key.split(".")
        node: Any = self._data
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, default)
        return node

    def section(self, key: str) -> dict[str, Any]:
        """Return a top-level section as a dict (empty dict if missing)."""
        value = self._data.get(key, {})
        return value if isinstance(value, dict) else {}

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Config(keys={list(self._data.keys())})"


# ── Module-level helpers ──────────────────────────────────────────────────────

_default_config: Config | None = None


def get_default_config() -> Config:
    """Return the process-wide default Config (loaded once, cached)."""
    global _default_config
    if _default_config is None:
        _default_config = Config()
    return _default_config


def load_config(path: str | Path | None = None) -> Config:
    """
    Create and return a Config instance.

    Parameters
    ----------
    path:
        Path to a custom YAML file.  When *None* only the bundled defaults
        are loaded.
    """
    return Config(path)
