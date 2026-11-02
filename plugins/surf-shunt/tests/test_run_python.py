import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RUN_PYTHON = Path(__file__).resolve().parents[1] / "scripts" / "run-python"
OLD_PYTHON = "#!/bin/sh\n[ \"$1\" = --version ] && echo 'Python 3.9.6'\nexit 1\n"


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    """A PATH holding only the tools run-python needs, so the host's own pythons stay out of it."""
    directory = tmp_path / "bin"
    directory.mkdir()
    for tool in ["date", "mkdir"]:
        (directory / tool).symlink_to(shutil.which(tool))
    return directory


def install_python(bin_dir: Path, name: str, script: str | None = None) -> None:
    target = bin_dir / name
    if script is None:
        target.symlink_to(sys.executable)
    else:
        target.write_text(script)
        target.chmod(0o755)


def run(bin_dir: Path, tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    script = tmp_path / "hello.py"
    script.write_text("import sys; print(f'ran {sys.version_info >= (3, 10)}'); sys.exit(3)")
    return subprocess.run(
        [str(RUN_PYTHON), *args, str(script)],
        capture_output=True,
        text=True,
        env={"PATH": str(bin_dir), "CLAUDE_PLUGIN_DATA": str(tmp_path / "data"), "HOME": str(tmp_path)},
    )


@pytest.mark.parametrize(
    "pythons",
    [
        pytest.param({"python3": None}, id="python3-is-new-enough"),
        pytest.param({"python3": OLD_PYTHON, "python3.12": None}, id="falls-back-to-versioned"),
    ],
)
def test_runs_script_with_suitable_python(bin_dir: Path, tmp_path: Path, pythons: dict):
    for name, script in pythons.items():
        install_python(bin_dir, name, script)

    result = run(bin_dir, tmp_path)

    assert result.stdout == "ran True\n"
    assert result.returncode == 3


@pytest.mark.parametrize(
    ("args", "expected_exit", "shows_system_message"),
    [
        pytest.param(["--fail-open"], 0, True, id="hook-fails-open"),
        pytest.param([], 1, False, id="script-fails"),
    ],
)
def test_warns_without_suitable_python(bin_dir, tmp_path, args, expected_exit, shows_system_message):
    install_python(bin_dir, "python3", OLD_PYTHON)

    result = run(bin_dir, tmp_path, *args)

    assert result.returncode == expected_exit
    assert "needs Python >= 3.10, but PATH only has Python 3.9.6" in result.stderr
    assert ("systemMessage" in result.stdout) == shows_system_message
    if shows_system_message:
        assert "Python 3.9.6" in json.loads(result.stdout)["systemMessage"]
    assert "needs Python >= 3.10" in (tmp_path / "data" / "surf-shunt.log").read_text()


def test_warns_without_any_python(bin_dir: Path, tmp_path: Path):
    result = run(bin_dir, tmp_path, "--fail-open")
    assert result.returncode == 0
    assert "no python3" in json.loads(result.stdout)["systemMessage"]


def test_wrapper_is_executable():
    assert os.access(RUN_PYTHON, os.X_OK)
