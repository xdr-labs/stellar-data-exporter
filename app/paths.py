from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def default_state_dir(
    package_dir: Path,
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    env = os.environ if environ is None else environ

    explicit = env.get("STELLAR_EXPORTER_STATE_DIR")
    if explicit:
        return Path(explicit).expanduser()

    source_root = package_dir.parent
    if (source_root / "pyproject.toml").is_file():
        return source_root / ".data"

    xdg_state_home = env.get("XDG_STATE_HOME")
    if xdg_state_home:
        return Path(xdg_state_home).expanduser() / "stellar-data-exporter"

    user_home = Path.home() if home is None else home
    return user_home / ".local" / "state" / "stellar-data-exporter"
