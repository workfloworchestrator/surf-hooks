#!/usr/bin/env python3
"""
Claude Code Hook: BaseException Enforcer
PostToolUse hook for Edit|Write|MultiEdit events.

Hard-blocks any use of BaseException in Python files:
  - Subclassing: class Foo(BaseException)
  - Catching:    except BaseException
  - Raising:     raise BaseException(...)

Exit code 2 = hard block (Claude must refactor before proceeding)
"""

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BaseExceptionIssue:
    lineno: int
    kind: str  # "subclass", "catch", "raise"


def _is_base_exception(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "BaseException"


class BaseExceptionAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.issues: list[BaseExceptionIssue] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        for base in node.bases:
            if _is_base_exception(base):
                self.issues.append(BaseExceptionIssue(lineno=node.lineno, kind="subclass"))
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        if _is_base_exception(node.type):
            self.issues.append(BaseExceptionIssue(lineno=node.lineno, kind="catch"))
        elif isinstance(node.type, ast.Tuple) and any(
            _is_base_exception(e) for e in node.type.elts
        ):
            self.issues.append(BaseExceptionIssue(lineno=node.lineno, kind="catch"))
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise):
        if node.exc is not None:
            exc = node.exc
            if _is_base_exception(exc) or (
                isinstance(exc, ast.Call) and _is_base_exception(exc.func)
            ):
                self.issues.append(BaseExceptionIssue(lineno=node.lineno, kind="raise"))
        self.generic_visit(node)


_BLOCK_MESSAGES = {
    "subclass": (
        "Subclass `Exception` (or a more specific type) instead. "
        "`BaseException` includes `SystemExit`, `KeyboardInterrupt`, and `GeneratorExit`, "
        "which must not be subclassed in application code."
    ),
    "catch": (
        "Catch `Exception` (or a more specific type) instead. "
        "Catching `BaseException` silences `SystemExit` and `KeyboardInterrupt`."
    ),
    "raise": (
        "Raise `Exception` (or a more specific type) instead. "
        "Define a custom exception class if needed."
    ),
}


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path: str = (
        event.get("tool_input", {}).get("file_path", "")
        or event.get("tool_input", {}).get("path", "")
    )
    if not file_path.endswith(".py"):
        sys.exit(0)

    content: str = event.get("tool_input", {}).get("new_content", "")
    if not content:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            sys.exit(0)

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        sys.exit(0)

    analyzer = BaseExceptionAnalyzer()
    analyzer.visit(tree)

    if not analyzer.issues:
        sys.exit(0)

    for issue in analyzer.issues:
        print(
            f"BLOCKED: `BaseException` {issue.kind} at line {issue.lineno} in `{file_path}`. "
            f"{_BLOCK_MESSAGES[issue.kind]}",
            file=sys.stderr,
        )
    sys.exit(2)


if __name__ == "__main__":
    main()
