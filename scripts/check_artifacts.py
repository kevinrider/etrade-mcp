"""Verify built distributions through isolated installations, without brokerage access."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def check_contents(names: list[str], required: set[str]) -> None:
    missing = required.difference(names)
    if missing:
        raise RuntimeError(f"Missing archive entries: {sorted(missing)}")
    forbidden = {".git", ".venv", ".idea", ".vscode", "__pycache__", "dist", "build"}
    for name in names:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or forbidden.intersection(path.parts)
            or any(part.startswith(".env") for part in path.parts)
            or "credentials" in path.name.lower()
            or path.suffix in {".pyc", ".pyo", ".pem"}
        ):
            raise RuntimeError(f"Unexpected archive entry: {name}")


def main() -> None:
    wheels = sorted((ROOT / "dist").glob("*.whl"))
    sources = sorted((ROOT / "dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise RuntimeError("Expected exactly one wheel and one sdist; run uv build --clear")

    with zipfile.ZipFile(wheels[0]) as archive:
        check_contents(
            archive.namelist(),
            {"etrade_mcp/__init__.py", "etrade_mcp/_version.py", "etrade_mcp/py.typed"},
        )
    with tarfile.open(sources[0]) as archive:
        check_contents(
            [name.partition("/")[2] for name in archive.getnames()],
            {
                "src/etrade_mcp/__init__.py",
                "src/etrade_mcp/_version.py",
                "src/etrade_mcp/py.typed",
                "scripts/check_artifacts.py",
                "LICENSE",
                "pyproject.toml",
                "uv.lock",
            },
        )

    # -I excludes the checkout and inherited Python path settings from imports.
    probe = """
from importlib.metadata import metadata, version
from importlib.resources import files
from pathlib import Path
import etrade_mcp
import sys

assert etrade_mcp.__version__ == version('etrade-mcp')
assert metadata('etrade-mcp')['License-Expression'] == 'Apache-2.0'
assert files('etrade_mcp').joinpath('py.typed').is_file()
assert Path(etrade_mcp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
print(f'Installed etrade-mcp {etrade_mcp.__version__} on Python {sys.version.split()[0]}')
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    # The repository is in planning status; use metadata rather than a second
    # hard-coded version so every future artifact must match the source version.
    namespace: dict[str, object] = {}
    exec((ROOT / "src/etrade_mcp/_version.py").read_text(), namespace)
    expected_version = str(namespace["__version__"])
    probe += f"\nassert version('etrade-mcp') == {expected_version!r}\n"

    with tempfile.TemporaryDirectory(prefix="etrade-mcp-artifacts-") as temporary:
        outside = Path(temporary)
        for kind, artifact in (("wheel", wheels[0]), ("sdist", sources[0])):
            venv = outside / kind
            subprocess.run(
                ["uv", "venv", "--python", sys.executable, str(venv)],
                cwd=outside,
                env=environment,
                check=True,
            )
            python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            subprocess.run(
                ["uv", "pip", "install", "--python", str(python), str(artifact)],
                cwd=outside,
                env=environment,
                check=True,
            )
            subprocess.run(
                [str(python), "-I", "-c", probe], cwd=outside, env=environment, check=True
            )
            print(f"Verified {kind}: {artifact.name}", flush=True)


if __name__ == "__main__":
    main()
