#!/usr/bin/env python3
from __future__ import annotations

import argparse
import tarfile
import zipfile
from pathlib import Path

from app import __version__


SDIST_REQUIRED = {
    ".engineering/project.yaml",
    ".engineering/release.yaml",
    ".engineering/tests.yaml",
    "deploy/nginx/stellar-data-exporter.conf",
    "deploy/systemd/stellar-data-exporter.service",
    "docs/PRODUCTION.md",
    "scripts/backup-state.sh",
    "scripts/restore-test.sh",
    "scripts/release-preflight.sh",
    "scripts/release-qualify.sh",
    "scripts/hash-release-artifacts.sh",
    "schemas/runtime-contract.schema.json",
    "tools/runtime-contract.py",
}

WHEEL_REQUIRED = {
    "app/static/app.js",
    "app/static/index.html",
    "app/static/stellar-cyber-logo.svg",
    "app/static/styles.css",
}


def normalized_sdist_names(archive: Path) -> set[str]:
    with tarfile.open(archive, "r:gz") as bundle:
        return {
            name.split("/", 1)[1]
            for name in bundle.getnames()
            if "/" in name
        }


def wheel_contents(archive: Path) -> tuple[set[str], str, str]:
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        metadata = next(name for name in names if name.endswith(".dist-info/METADATA"))
        entry_points = next(
            (name for name in names if name.endswith(".dist-info/entry_points.txt")),
            None,
        )
        return (
            names,
            bundle.read(metadata).decode("utf-8"),
            bundle.read(entry_points).decode("utf-8") if entry_points else "",
        )


def require_all(actual: set[str], required: set[str], label: str) -> None:
    missing = sorted(required - actual)
    if missing:
        raise SystemExit(f"{label} missing: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dist_dir", type=Path)
    args = parser.parse_args()

    sdists = sorted(args.dist_dir.glob("*.tar.gz"))
    wheels = sorted(args.dist_dir.glob("*.whl"))
    if len(sdists) != 1 or len(wheels) != 1:
        raise SystemExit("expected exactly one sdist and one wheel")

    require_all(normalized_sdist_names(sdists[0]), SDIST_REQUIRED, "sdist")
    wheel_names, metadata, entry_points = wheel_contents(wheels[0])
    require_all(wheel_names, WHEEL_REQUIRED, "wheel")

    for value in (
        f"Version: {__version__}",
        "Project-URL: Repository, https://github.com/xdr-labs/stellar-data-exporter",
        "Project-URL: Issues, https://github.com/xdr-labs/stellar-data-exporter/issues",
        "Description-Content-Type: text/markdown",
    ):
        if value not in metadata:
            raise SystemExit(f"wheel metadata missing: {value}")

    if "stellar-data-exporter = app.cli:main" not in entry_points:
        raise SystemExit("wheel console entry point missing: stellar-data-exporter = app.cli:main")

    print("RELEASE_ARTIFACTS=PASS")


if __name__ == "__main__":
    main()
