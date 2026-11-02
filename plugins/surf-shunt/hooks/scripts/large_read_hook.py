#!/usr/bin/env python3
"""
Claude Code Hook: Large Read Shunt
PreToolUse hook for Read and Bash events.

Blocks reading large files straight into Claude's context and points Claude at
the bulk-reader skill, which hands the files to an on-prem model instead:
  - Read without offset/limit on a file over the line threshold
  - Bash `cat` / `less` / `more` / `bat` on a file over the line threshold

Targeted reads pass through: Read with offset/limit, head/tail, sed -n, and any
command whose output is piped or redirected.

Configuration (environment):
  SURF_SHUNT_MIN_LINES   line threshold (default: 350)
  SURF_SHUNT_DISABLE     set to 1 to turn the hook off (e.g. while the model is down)

Exit code 2 = block (stderr is shown to Claude)
"""

import json
import os
import shlex
import sys
from itertools import chain, groupby
from pathlib import Path

DEFAULT_MIN_LINES = 350
READ_COMMANDS = frozenset({"cat", "less", "more", "bat"})
SEGMENT_SEPARATORS = frozenset({";", "&&", "||", "&"})
PIPES_AND_REDIRECTS = frozenset({"|", "|&", ">", ">>", ">&", "&>", ">|"})
# Read renders these natively; their newline count says nothing about context cost
NON_TEXT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".ipynb"})
SHUNT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "shunt.py"


def min_lines() -> int:
    value = os.environ.get("SURF_SHUNT_MIN_LINES", "")
    return int(value) if value.isdigit() else DEFAULT_MIN_LINES


def count_lines(path: Path) -> int:
    if path.suffix.lower() in NON_TEXT_SUFFIXES or not path.is_file():
        return 0
    try:
        with path.open("rb") as handle:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: handle.read(1 << 16), b""))
    except OSError:
        return 0


def read_targets(tool_input: dict) -> list[str]:
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return []
    return [tool_input["file_path"]] if tool_input.get("file_path") else []


def _tokenize(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return []


def _segment_file_args(segment: list[str]) -> list[str]:
    match segment:
        case [command, *args] if Path(command).name in READ_COMMANDS:
            return [arg for arg in args if not arg.startswith("-")]
        case _:
            return []


def bash_targets(command: str) -> list[str]:
    tokens = _tokenize(command)
    if PIPES_AND_REDIRECTS.intersection(tokens):
        return []
    segments = [
        list(group)
        for is_separator, group in groupby(tokens, key=lambda token: token in SEGMENT_SEPARATORS)
        if not is_separator
    ]
    return list(chain.from_iterable(_segment_file_args(segment) for segment in segments))


def block_message(oversized: list[tuple[str, int]], threshold: int) -> str:
    listing = ", ".join(f"`{path}` ({lines} lines)" for path, lines in oversized)
    paths = shlex.join(path for path, _ in oversized)
    return (
        f"BLOCKED: {listing} exceeds the {threshold}-line threshold. "
        "Delegate the read to the on-prem model with the surf-shunt bulk-reader skill:\n"
        f'  python3 {SHUNT_SCRIPT} bulk-read --question "<your question>" --paths {paths}\n'
        "If you need exact content for an edit, use Read with offset/limit for just that section."
    )


def main():
    if os.environ.get("SURF_SHUNT_DISABLE", "").lower() in {"1", "true", "yes"}:
        sys.exit(0)

    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_input = event.get("tool_input") or {}
    match event.get("tool_name"):
        case "Read":
            paths = read_targets(tool_input)
        case "Bash":
            paths = bash_targets(tool_input.get("command", ""))
        case _:
            paths = []

    cwd = Path(event.get("cwd") or ".")
    threshold = min_lines()
    oversized = [(path, lines) for path in paths if (lines := count_lines(cwd / path)) > threshold]
    if not oversized:
        sys.exit(0)

    print(block_message(oversized, threshold), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
