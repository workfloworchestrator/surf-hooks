#!/usr/bin/env python3
"""
Claude Code Hook: Python Style Enforcer
PostToolUse hook for Edit|Write events.

Analyzes written Python files for:
  - for loops with break/continue
  - Nested for loops beyond a configurable depth
  - Suggests itertools, list comprehensions, helper functions

Communicates back to Claude via stdout JSON (additionalContext / decision).
Exit code 0  = allow, but inject feedback
Exit code 2  = block (hard reject; use sparingly)
"""

import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Configuration ────────────────────────────────────────────────────────────

MAX_NESTING_DEPTH = 1          # Max for-loop nesting allowed before nudge
HARD_BLOCK_DEPTH  = 3          # Nesting at or above this triggers exit code 2 (hard reject)
HARD_BLOCK_BREAKS = False      # Set True to hard-reject break/continue; False = nudge only

# ── AST Visitors ─────────────────────────────────────────────────────────────

@dataclass
class ForLoopIssue:
    lineno: int
    kind: str          # "break", "continue", "nesting"
    depth: int = 0
    detail: str = ""


class ForLoopAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.issues: list[ForLoopIssue] = []
        self._depth = 0

    def visit_For(self, node: ast.For):
        self._depth += 1

        if self._depth > MAX_NESTING_DEPTH:
            self.issues.append(ForLoopIssue(
                lineno=node.lineno,
                kind="nesting",
                depth=self._depth,
                detail=f"for-loop nested {self._depth} levels deep (max {MAX_NESTING_DEPTH})"
            ))

        # Check body for break / continue directly under this for
        for child in ast.walk(node):
            if isinstance(child, ast.For) and child is not node:
                # Don't double-count nested for-loop bodies; visitor handles those
                continue
            if isinstance(child, ast.Break):
                self.issues.append(ForLoopIssue(
                    lineno=child.lineno,
                    kind="break",
                    depth=self._depth,
                    detail="break inside for-loop"
                ))
            elif isinstance(child, ast.Continue):
                self.issues.append(ForLoopIssue(
                    lineno=child.lineno,
                    kind="continue",
                    depth=self._depth,
                    detail="continue inside for-loop"
                ))

        self.generic_visit(node)
        self._depth -= 1

    def visit_While(self, node):
        # Don't count while-loops toward for-loop depth, but still descend
        self.generic_visit(node)


# ── Suggestion Builder ───────────────────────────────────────────────────────

def build_feedback(issues: list[ForLoopIssue], filepath: str) -> Optional[str]:
    if not issues:
        return None

    break_continues = [i for i in issues if i.kind in ("break", "continue")]
    nestings        = [i for i in issues if i.kind == "nesting"]

    lines = [f"## Python style feedback for `{filepath}`\n"]

    if break_continues:
        lines.append("### ⚠️  break / continue detected")
        for i in break_continues:
            lines.append(f"- Line {i.lineno}: `{i.kind}` — consider refactoring")
        lines.append(
            "\n**Preferred alternatives:**\n"
            "- Replace `break` with `itertools.takewhile()` or `next(filter(...), None)`\n"
            "- Replace `continue` with a negated condition in a list comprehension or `filter()`\n"
            "- Extract the loop body into a helper function with an early `return`\n"
        )

    if nestings:
        lines.append("### ⚠️  Deep for-loop nesting detected")
        for i in nestings:
            lines.append(f"- Line {i.lineno}: {i.detail}")
        lines.append(
            "\n**Preferred alternatives:**\n"
            "- Use `itertools.product()` instead of nested for-loops over cartesian products\n"
            "- Use `itertools.chain.from_iterable()` to flatten nested iterations\n"
            "- Extract inner loop(s) into a named helper function\n"
            "- Use a list/generator comprehension with a single iterable\n"
        )

    lines.append(
        "\n**General guidance:** Prefer `itertools`, list/generator comprehensions, "
        "and small helper functions over imperative for-loops with control-flow statements. "
        "Rewrite the affected section before proceeding."
    )

    return "\n".join(lines)


# ── Hard-block decision ──────────────────────────────────────────────────────

def should_hard_block(issues: list[ForLoopIssue]) -> tuple[bool, str]:
    for i in issues:
        if i.kind == "nesting" and i.depth >= HARD_BLOCK_DEPTH:
            return True, (
                f"BLOCKED: for-loop nested {i.depth} levels (line {i.lineno}). "
                f"Max allowed is {HARD_BLOCK_DEPTH - 1}. "
                "Refactor using itertools or helper functions first."
            )
        if HARD_BLOCK_BREAKS and i.kind in ("break", "continue"):
            return True, (
                f"BLOCKED: `{i.kind}` at line {i.lineno}. "
                "Use itertools / filter / helper functions instead."
            )
    return False, ""


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)   # Can't parse input — pass through silently

    # Only care about Python files
    file_path: str = (
        event.get("tool_input", {}).get("file_path", "")
        or event.get("tool_input", {}).get("path", "")
    )
    if not file_path.endswith(".py"):
        sys.exit(0)

    # Get file content — prefer new_content from the event, else read from disk
    content: str = event.get("tool_input", {}).get("new_content", "")
    if not content:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            sys.exit(0)

    # Parse AST
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        sys.exit(0)   # Syntax errors are Claude's problem, not ours

    analyzer = ForLoopAnalyzer()
    analyzer.visit(tree)

    if not analyzer.issues:
        sys.exit(0)   # All good

    # Check for hard block first
    block, reason = should_hard_block(analyzer.issues)
    if block:
        print(reason, file=sys.stderr)
        sys.exit(2)

    # Otherwise: build nudge feedback and inject as additionalContext
    feedback = build_feedback(analyzer.issues, file_path)
    if feedback:
        # PostToolUse uses top-level decision/reason format
        output = {
            "decision": "block",          # Tell Claude to reconsider
            "reason": feedback
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
