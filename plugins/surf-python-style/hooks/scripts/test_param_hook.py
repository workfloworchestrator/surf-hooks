#!/usr/bin/env python3
"""
Claude Code Hook: Test Parameterization Nudger
PostToolUse hook for Edit|Write events on test files.

Detects patterns that suggest manual test duplication instead of
@pytest.mark.parametrize (or unittest equivalents):

  1. Structural clones — multiple test_* functions in the same class/module
     whose AST bodies are identical modulo literal values (strings, numbers,
     booleans).  Threshold: MIN_CLONE_GROUP_SIZE or more clones = nudge.

  2. Inline data tables — a test function whose body contains a literal list
     of tuples/dicts that is then iterated over with a for-loop.

  3. Missing parametrize — a test class that has many test_* methods but
     zero use of parametrize / subtests / pytest.param anywhere in the file.

Communicates back to Claude via stdout JSON decision/reason.
Exit code 0 = pass through silently (no issues found)
"""

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────

MIN_CLONE_GROUP_SIZE   = 2    # Number of structurally identical tests to trigger nudge
MIN_METHODS_FOR_CHECK  = 4    # Only check classes/modules with at least this many test_ methods
INLINE_TABLE_MIN_ROWS  = 2    # Inline list-of-tuples/dicts with >= this many entries = nudge

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_test_file(path: str) -> bool:
    p = Path(path)
    return p.suffix == ".py" and (
        p.name.startswith("test_")
        or p.name.endswith("_test.py")
        or "test" in p.parts
    )


def _uses_parametrize(tree: ast.AST) -> bool:
    """True if the file uses @pytest.mark.parametrize, subTest, or pytest.param anywhere."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("parametrize", "param"):
            return True
        if isinstance(node, ast.Name) and node.id in ("subTest", "parametrize"):
            return True
        if isinstance(node, ast.Str) and "parametrize" in node.s:
            return True
    return False


def _normalize_literals(node: ast.AST) -> ast.AST:
    """
    Return a copy of the AST subtree with all literal values replaced by a
    placeholder constant so that structurally identical code with different
    test data compares equal.
    """
    class LiteralNormalizer(ast.NodeTransformer):
        def visit_Constant(self, n):
            return ast.Constant(value="__LIT__")
        def visit_JoinedStr(self, n):          # f-strings
            return ast.Constant(value="__LIT__")
        def visit_UnaryOp(self, n):            # -1, +1, ~x on literals
            if isinstance(n.operand, ast.Constant):
                return ast.Constant(value="__LIT__")
            return self.generic_visit(n)

    import copy
    return LiteralNormalizer().visit(copy.deepcopy(node))


def _body_signature(func: ast.FunctionDef) -> str:
    """Canonical string of a function body (not name) with literals normalised."""
    try:
        # Build a temporary module with just the body statements so the
        # function name does not influence the signature.
        body_module = ast.Module(body=func.body, type_ignores=[])
        ast.fix_missing_locations(body_module)
        normalized = _normalize_literals(body_module)
        return ast.unparse(normalized)
    except Exception:
        return ""


# ── Detectors ─────────────────────────────────────────────────────────────────

class ParametrizeIssue:
    def __init__(self, kind: str, detail: str, lineno: int, names: list[str] = None):
        self.kind    = kind       # "clone", "inline_table", "no_parametrize"
        self.detail  = detail
        self.lineno  = lineno
        self.names   = names or []


def detect_clone_tests(funcs: list[ast.FunctionDef]) -> list[ParametrizeIssue]:
    """Find groups of test functions with structurally identical bodies."""
    issues = []
    sig_to_funcs: dict[str, list[ast.FunctionDef]] = defaultdict(list)

    for f in funcs:
        if not f.name.startswith("test_"):
            continue
        sig = _body_signature(f)
        if sig:
            sig_to_funcs[sig].append(f)

    for sig, group in sig_to_funcs.items():
        if len(group) >= MIN_CLONE_GROUP_SIZE:
            names = [f.name for f in group]
            issues.append(ParametrizeIssue(
                kind="clone",
                detail=(
                    f"{len(group)} structurally identical test functions "
                    f"(differ only in literal values): {', '.join(names)}"
                ),
                lineno=group[0].lineno,
                names=names,
            ))

    return issues


def detect_inline_tables(funcs: list[ast.FunctionDef]) -> list[ParametrizeIssue]:
    """
    Find test functions that manually build a list of tuples/dicts and iterate
    over them — the classic 'roll-your-own parametrize' pattern.
    """
    issues = []

    for f in funcs:
        if not f.name.startswith("test_"):
            continue
        for node in ast.walk(f):
            # Look for: cases = [...] where elements are Tuple or Dict
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value if isinstance(node, ast.Assign) else getattr(node, "value", None)
            if not isinstance(value, ast.List):
                continue
            elts = value.elts
            if len(elts) < INLINE_TABLE_MIN_ROWS:
                continue
            if all(isinstance(e, (ast.Tuple, ast.Dict)) for e in elts):
                issues.append(ParametrizeIssue(
                    kind="inline_table",
                    detail=(
                        f"`{f.name}` (line {f.lineno}) builds an inline data table "
                        f"with {len(elts)} entries and iterates over it manually"
                    ),
                    lineno=f.lineno,
                    names=[f.name],
                ))
                break   # one issue per function is enough

    return issues


def detect_unparameterized_class(cls: ast.ClassDef) -> Optional[ParametrizeIssue]:
    """Flag a test class with many test_ methods and zero parametrize usage."""
    test_methods = [
        n for n in ast.walk(cls)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
    ]
    if len(test_methods) < MIN_METHODS_FOR_CHECK:
        return None

    # Check for any parametrize use within the class
    for node in ast.walk(cls):
        if isinstance(node, ast.Attribute) and node.attr in ("parametrize", "param"):
            return None
        if isinstance(node, ast.Name) and node.id == "subTest":
            return None

    return ParametrizeIssue(
        kind="no_parametrize",
        detail=(
            f"class `{cls.name}` (line {cls.lineno}) has {len(test_methods)} test methods "
            "but no `@pytest.mark.parametrize` or `subTest` usage"
        ),
        lineno=cls.lineno,
        names=[m.name for m in test_methods],
    )


# ── Feedback Builder ──────────────────────────────────────────────────────────

def build_feedback(issues: list[ParametrizeIssue], filepath: str) -> str:
    lines = [f"## Test parameterization feedback for `{filepath}`\n"]

    for issue in issues:
        if issue.kind == "clone":
            lines.append(f"### ⚠️  Duplicate test structure (line {issue.lineno})")
            lines.append(f"- {issue.detail}")
            lines.append(
                "\n**Preferred fix:** Collapse into a single test using "
                "`@pytest.mark.parametrize`:\n"
                "```python\n"
                "@pytest.mark.parametrize(\"input,expected\", [\n"
                "    (case1_input, case1_expected),\n"
                "    (case2_input, case2_expected),\n"
                "])\n"
                "def test_thing(input, expected):\n"
                "    assert my_func(input) == expected\n"
                "```\n"
            )

        elif issue.kind == "inline_table":
            lines.append(f"### ⚠️  Manual data table in test (line {issue.lineno})")
            lines.append(f"- {issue.detail}")
            lines.append(
                "\n**Preferred fix:** Move the data table to `@pytest.mark.parametrize` "
                "so each row gets its own test ID, pass/fail, and traceback:\n"
                "```python\n"
                "@pytest.mark.parametrize(\"x,y\", [\n"
                "    (row1_x, row1_y),\n"
                "    (row2_x, row2_y),\n"
                "])\n"
                "def test_thing(x, y):\n"
                "    ...\n"
                "```\n"
                "For more complex fixtures use `pytest.param(..., id='label')` to name cases.\n"
            )

        elif issue.kind == "no_parametrize":
            lines.append(f"### ⚠️  Large test class without parametrize (line {issue.lineno})")
            lines.append(f"- {issue.detail}")
            lines.append(
                "\n**Preferred fix:** Review whether any methods are structural clones "
                "and consolidate with `@pytest.mark.parametrize`. "
                "For unittest-style classes use `self.subTest(case=...)` or migrate to pytest.\n"
            )

    lines.append(
        "\n**General guidance:** Each distinct input/output pair should be a parametrize case, "
        "not a separate function. This gives individual test IDs, isolated failures, "
        "and a single source of truth for the test logic. "
        "Rewrite the affected tests before proceeding."
    )

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path: str = (
        event.get("tool_input", {}).get("file_path", "")
        or event.get("tool_input", {}).get("path", "")
    )

    if not _is_test_file(file_path):
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

    # If the file already uses parametrize broadly, stay quiet
    if _uses_parametrize(tree):
        # Still check for inline tables — parametrize elsewhere doesn't excuse this
        all_funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        inline_issues = detect_inline_tables(all_funcs)
        if not inline_issues:
            sys.exit(0)
        issues = inline_issues
    else:
        all_funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        issues: list[ParametrizeIssue] = []
        issues += detect_clone_tests(all_funcs)
        issues += detect_inline_tables(all_funcs)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.startswith(("Test", "test")):
                ci = detect_unparameterized_class(node)
                if ci:
                    issues.append(ci)

    if not issues:
        sys.exit(0)

    feedback = build_feedback(issues, file_path)
    output = {
        "decision": "block",
        "reason": feedback,
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
