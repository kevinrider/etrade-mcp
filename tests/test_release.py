"""Offline checks for the release metadata gate; no publishing or Git calls."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from etrade_mcp import __version__
from scripts.check_release import ReleaseValidationError, validate_release


@pytest.fixture
def release_tree(tmp_path: Path) -> Path:
    (tmp_path / "src/etrade_mcp").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "etrade-mcp"\ndynamic = ["version"]\n'
        '[tool.hatch.version]\npath = "src/etrade_mcp/_version.py"\n'
    )
    (tmp_path / "src/etrade_mcp/_version.py").write_text('__version__ = "0.1.0"\n')
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "etrade-mcp"\nversion = "0.1.0"\nsource = { editable = "." }\n'
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n\nInitial release.\n")
    return tmp_path


def test_matching_release_and_real_checkout(release_tree: Path) -> None:
    assert validate_release(release_tree, "v0.1.0") == "0.1.0"
    assert validate_release(Path(__file__).resolve().parents[1], f"v{__version__}") == __version__


@pytest.mark.parametrize("tag", ["0.1.0", "v1.0.0", "v0.1.0a1", "v0.1.0\n", "v0.1.0;echo unsafe"])
def test_mismatched_tag_is_rejected(release_tree: Path, tag: str) -> None:
    with pytest.raises(ReleaseValidationError, match="tag"):
        validate_release(release_tree, tag)


@pytest.mark.parametrize("version", ["0.1", "0.1.0a1", "0.1.0.post1", "0.1.0+local", "00.1.0"])
def test_unsupported_version_is_rejected(release_tree: Path, version: str) -> None:
    (release_tree / "src/etrade_mcp/_version.py").write_text(f'__version__ = "{version}"\n')
    with pytest.raises(ReleaseValidationError, match="three numeric"):
        validate_release(release_tree, f"v{version}")


@pytest.mark.parametrize(
    "filename,content",
    [
        (
            "uv.lock",
            '[[package]]\nname = "etrade-mcp"\nversion = "0.2.0"\nsource = { editable = "." }\n',
        ),
        (
            "uv.lock",
            '[[package]]\nname = "another-package"\nversion = "0.1.0"\n'
            'source = { editable = "." }\n',
        ),
        (
            "uv.lock",
            '[[package]]\nname = "etrade-mcp"\nversion = "0.1.0"\nsource = { editable = "." }\n'
            * 2,
        ),
        ("CHANGELOG.md", "# Changelog\n\n## 0.1.01\n"),
        ("src/etrade_mcp/_version.py", '__version__ = "0.1.0"\n__version__ = "0.1.0"\n'),
        ("src/etrade_mcp/_version.py", '__version__ = str("0.1.0")\n'),
    ],
)
def test_inconsistent_release_files_are_rejected(
    release_tree: Path, filename: str, content: str
) -> None:
    (release_tree / filename).write_text(content)
    with pytest.raises(ReleaseValidationError):
        validate_release(release_tree, "v0.1.0")


@pytest.mark.parametrize(
    "old,new",
    [
        ('name = "etrade-mcp"', 'name = "another-package"'),
        ('dynamic = ["version"]', 'version = "0.1.0"'),
        ("src/etrade_mcp/_version.py", "another_version.py"),
    ],
)
def test_project_version_source_is_enforced(release_tree: Path, old: str, new: str) -> None:
    path = release_tree / "pyproject.toml"
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(ReleaseValidationError):
        validate_release(release_tree, "v0.1.0")


@pytest.mark.parametrize("tag,code", [("v0.1.0", 0), ("v0.2.0", 1)])
def test_release_gate_cli(release_tree: Path, tag: str, code: int) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py", "--root", str(release_tree)],
        env={**os.environ, "RELEASE_TAG": tag},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == code
    if code == 0:
        assert result.stdout.strip() == "Release v0.1.0 metadata verified."
    else:
        assert "Release validation failed" in result.stderr
        assert "Traceback" not in result.stderr


def test_dynamic_root_lockfile_can_omit_version(release_tree: Path) -> None:
    (release_tree / "uv.lock").write_text(
        '[[package]]\nname = "etrade-mcp"\nsource = { editable = "." }\n'
    )
    assert validate_release(release_tree, "v0.1.0") == "0.1.0"


def test_lockfile_must_reference_the_checkout(release_tree: Path) -> None:
    path = release_tree / "uv.lock"
    path.write_text(path.read_text().replace('editable = "."', 'editable = "../another-project"'))
    with pytest.raises(ReleaseValidationError, match="editable root"):
        validate_release(release_tree, "v0.1.0")
