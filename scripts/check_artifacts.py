"""Verify built distributions through isolated installations, without brokerage access."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from etrade_mcp.guidance import catalog

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

    guidance_assets = {
        "etrade_mcp/descriptions/fields.toml",
        *(f"etrade_mcp/descriptions/{name}.md" for name in catalog().tools),
    }
    with zipfile.ZipFile(wheels[0]) as archive:
        check_contents(
            archive.namelist(),
            {
                "etrade_mcp/__init__.py",
                "etrade_mcp/_version.py",
                "etrade_mcp/py.typed",
                "etrade_mcp/cli.py",
                "etrade_mcp/server.py",
                "etrade_mcp/http.py",
                "etrade_mcp/config.py",
                "etrade_mcp/tool_logging.py",
                "etrade_mcp/order_families.py",
                "etrade_mcp/tools/specialized.py",
            }
            | guidance_assets,
        )
    with tarfile.open(sources[0]) as archive:
        check_contents(
            [name.partition("/")[2] for name in archive.getnames()],
            {
                "src/etrade_mcp/__init__.py",
                "src/etrade_mcp/_version.py",
                "src/etrade_mcp/py.typed",
                "scripts/check_artifacts.py",
                "scripts/protocol_smoke.py",
                "README.md",
                "tests/test_http.py",
                "tests/test_cli.py",
                "tests/test_tool_logging.py",
                "tests/tool_logging_worker.py",
                "tests/test_specialized_previews.py",
                "tests/specialized_cases.py",
                "src/etrade_mcp/order_families.py",
                "src/etrade_mcp/tools/specialized.py",
                "LICENSE",
                "pyproject.toml",
                "uv.lock",
            }
            | {"src/" + name for name in guidance_assets},
        )

    # -I excludes the checkout and inherited Python path settings from imports.
    probe = """
from importlib.metadata import metadata, version
from importlib.resources import files
from pathlib import Path
import etrade_mcp
import sys
from etrade_mcp.guidance import catalog, tool_description

assert etrade_mcp.__version__ == version('etrade-mcp')
assert metadata('etrade-mcp')['License-Expression'] == 'Apache-2.0'
assert files('etrade_mcp').joinpath('py.typed').is_file()
assert len(catalog().tools) == 34
for name in catalog().tools:
    assert tool_description(name)
assert Path(etrade_mcp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
print(f'Installed etrade-mcp {etrade_mcp.__version__} on Python {sys.version.split()[0]}')
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    # Compare artifact metadata against the single source version.
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
            version_output = subprocess.check_output(
                [str(python), "-I", "-m", "etrade_mcp", "--version"],
                cwd=outside,
                env=environment,
                text=True,
            )
            assert version_output.strip() == expected_version
            help_output = subprocess.check_output(
                [str(python), "-I", "-m", "etrade_mcp", "serve", "--help"],
                cwd=outside,
                env={**environment, "NO_COLOR": "1", "TERM": "dumb"},
                text=True,
            )
            assert "--debug-tool-calls" in help_output
            executable = venv / ("Scripts/etrade-mcp.exe" if os.name == "nt" else "bin/etrade-mcp")
            assert (
                subprocess.check_output(
                    [str(executable), "--version"], cwd=outside, env=environment, text=True
                ).strip()
                == expected_version
            )
            subprocess.run(
                [str(python), "-I", str(ROOT / "scripts/protocol_smoke.py")],
                cwd=outside,
                env=environment,
                check=True,
                timeout=60,
            )
            print(f"Verified {kind}: {artifact.name}", flush=True)


if __name__ == "__main__":
    main()
