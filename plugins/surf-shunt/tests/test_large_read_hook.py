import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "scripts" / "large_read_hook.py"


def run_hook(event: dict, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **(env or {})},
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "big.py").write_text("x = 1\n" * 400)
    (tmp_path / "small.py").write_text("x = 1\n" * 10)
    (tmp_path / "huge image.png").write_bytes(b"\n" * 1000)
    return tmp_path


@pytest.mark.parametrize(
    ("tool_input", "expected_exit"),
    [
        pytest.param({"file_path": "big.py"}, 2, id="large-file-blocked"),
        pytest.param({"file_path": "small.py"}, 0, id="small-file-allowed"),
        pytest.param({"file_path": "big.py", "offset": 100}, 0, id="offset-allowed"),
        pytest.param({"file_path": "big.py", "limit": 50}, 0, id="limit-allowed"),
        pytest.param({"file_path": "big.py", "offset": 0}, 0, id="zero-offset-allowed"),
        pytest.param({"file_path": "missing.py"}, 0, id="missing-file-allowed"),
        pytest.param({"file_path": "huge image.png"}, 0, id="image-allowed"),
        pytest.param({}, 0, id="no-path-allowed"),
    ],
)
def test_read_tool(workspace: Path, tool_input: dict, expected_exit: int):
    result = run_hook({"tool_name": "Read", "tool_input": tool_input, "cwd": str(workspace)})
    assert result.returncode == expected_exit


@pytest.mark.parametrize(
    ("command", "expected_exit"),
    [
        pytest.param("cat big.py", 2, id="cat-large"),
        pytest.param("cat -n big.py", 2, id="cat-with-flag"),
        pytest.param("cat small.py big.py", 2, id="cat-second-arg"),
        pytest.param("cd . && cat big.py", 2, id="cat-after-and"),
        pytest.param("less big.py", 2, id="less-large"),
        pytest.param("/bin/cat big.py", 2, id="cat-absolute-path"),
        pytest.param("cat small.py", 0, id="cat-small"),
        pytest.param("cat big.py | grep x", 0, id="piped"),
        pytest.param("cat big.py > copy.py", 0, id="redirected"),
        pytest.param("cat big.py 2>/dev/null", 2, id="stderr-redirect-still-reads"),
        pytest.param("cat big.py 2>&1", 2, id="stderr-merged-still-reads"),
        pytest.param("cat big.py 1>copy.py", 0, id="explicit-stdout-redirect"),
        pytest.param("cat big.py &>copy.py", 0, id="both-streams-redirected"),
        pytest.param("cat < big.py", 2, id="input-redirect"),
        pytest.param("cat big.py; git diff | head", 2, id="pipe-in-other-segment"),
        pytest.param("seq 1 4 > out.txt; cat big.py", 2, id="redirect-in-other-segment"),
        pytest.param("cat small.py | grep x && cat big.py", 2, id="second-cat-not-piped"),
        pytest.param("grep x small.py | cat big.py", 2, id="cat-at-end-of-pipe"),
        pytest.param("cat big.py | head && cat small.py", 0, id="large-piped-small-direct"),
        pytest.param("head -50 big.py", 0, id="head-is-targeted"),
        pytest.param("tail big.py", 0, id="tail-is-targeted"),
        pytest.param("sed -n '1,40p' big.py", 0, id="sed-range-is-targeted"),
        pytest.param("grep -n x big.py", 0, id="grep"),
        pytest.param("git status", 0, id="unrelated"),
        pytest.param("cat 'unterminated", 0, id="unparseable"),
    ],
)
def test_bash_tool(workspace: Path, command: str, expected_exit: int):
    result = run_hook({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(workspace)})
    assert result.returncode == expected_exit


@pytest.mark.parametrize(
    ("env", "expected_exit"),
    [
        pytest.param({"SURF_SHUNT_MIN_LINES": "500"}, 0, id="raised-threshold"),
        pytest.param({"SURF_SHUNT_MIN_LINES": "abc"}, 2, id="invalid-threshold-uses-default"),
        pytest.param({"SURF_SHUNT_DISABLE": "1"}, 0, id="disabled"),
    ],
)
def test_configuration(workspace: Path, env: dict, expected_exit: int):
    event = {"tool_name": "Read", "tool_input": {"file_path": "big.py"}, "cwd": str(workspace)}
    assert run_hook(event, env).returncode == expected_exit


def test_block_message_names_the_command(workspace: Path):
    result = run_hook({"tool_name": "Read", "tool_input": {"file_path": "big.py"}, "cwd": str(workspace)})
    assert "`big.py` (400 lines)" in result.stderr
    assert "shunt.py bulk-read" in result.stderr
    assert "--paths big.py" in result.stderr


def test_ignores_other_tools(workspace: Path):
    result = run_hook({"tool_name": "Write", "tool_input": {"file_path": "big.py"}, "cwd": str(workspace)})
    assert result.returncode == 0


def test_ignores_malformed_input():
    result = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert result.returncode == 0
