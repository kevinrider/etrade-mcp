"""Validate ordinary release tags against the package's single version source."""

from __future__ import annotations

import argparse
import ast
import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_PATH = "src/etrade_mcp/_version.py"


class ReleaseValidationError(ValueError):
    """A release cannot safely proceed with inconsistent metadata."""


def validate_release(root: Path, tag: str) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text())
    metadata = project["project"]
    if metadata.get("name") != "etrade-mcp":
        raise ReleaseValidationError("Unexpected distribution name")
    if metadata.get("dynamic") != ["version"] or "version" in metadata:
        raise ReleaseValidationError("Expected a single dynamic package version")
    if project["tool"]["hatch"]["version"].get("path") != VERSION_PATH:
        raise ReleaseValidationError("Unexpected Hatch version source")
    tree = ast.parse((root / VERSION_PATH).read_text())
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    ]
    if len(assignments) != 1:
        raise ReleaseValidationError("Expected one literal package version")
    value = assignments[0].value
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise ReleaseValidationError("Expected one literal package version")
    version = value.value
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version) is None:
        raise ReleaseValidationError("Release version must have three numeric components")
    if tag != f"v{version}":
        raise ReleaseValidationError("Release tag does not match the package version")
    lock = tomllib.loads((root / "uv.lock").read_text())
    entries = [entry for entry in lock["package"] if entry["name"] == "etrade-mcp"]
    if len(entries) != 1 or entries[0].get("source") != {"editable": "."}:
        raise ReleaseValidationError("Lockfile must contain the editable root package")
    # uv omits the root version for dynamic metadata. If recorded, it must agree;
    # built and installed versions are checked independently by check_artifacts.
    if "version" in entries[0] and entries[0]["version"] != version:
        raise ReleaseValidationError("Lockfile package version does not match")
    changelog = (root / "CHANGELOG.md").read_text()
    if re.search(rf"^## {re.escape(version)}(?:\s|$)", changelog, re.MULTILINE) is None:
        raise ReleaseValidationError("Changelog has no entry for the release version")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=os.environ.get("RELEASE_TAG"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.tag is None:
        parser.error("Set RELEASE_TAG or pass --tag")
    try:
        version = validate_release(args.root, args.tag)
    except (OSError, SyntaxError, ValueError, KeyError):
        parser.exit(1, "Release validation failed: check tag, version, lockfile, and changelog.\n")
    print(f"Release v{version} metadata verified.")


if __name__ == "__main__":
    main()
