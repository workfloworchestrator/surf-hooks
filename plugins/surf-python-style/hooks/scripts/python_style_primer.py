#!/usr/bin/env python3
"""
Claude Code Hook: Python Style Primer (UserPromptSubmit)

Fires before every user prompt is processed. Injects a brief style
reminder into the conversation context so Claude prefers:
  - itertools over nested for-loops
  - list/generator comprehensions over for + append patterns
  - helper functions over break/continue

Only injects when the prompt seems Python-related to avoid noise.
"""

import json
import sys

PYTHON_KEYWORDS = {
    "def ", "class ", "import ", "python", ".py", "function",
    "loop", "iterate", "list", "dict", "generator", "comprehension",
    "for ", "while ", "async ", "script", "module", "refactor",
    "implement", "write", "code", "fix", "debug",
}

STYLE_PRIMER = (
    "[Project Python style rules] "
    "Prefer itertools (takewhile, chain, product, groupby, islice, filterfalse) "
    "and list/generator comprehensions over imperative for-loops. "
    "Avoid break and continue — use filter(), next(..., None), or early return in helper functions. "
    "Flatten nested for-loops with itertools.product() or chain.from_iterable(). "
    "Extract complex loop bodies into small, named helper functions. "
    "Prefer match/case over isinstance chains — use structural pattern matching "
    "when dispatching on type (especially union types and tagged variants). "
    "For tests: never duplicate test functions that differ only in their data — "
    "always use @pytest.mark.parametrize (or self.subTest for unittest). "
    "Each distinct input/output pair is a parametrize case, not a separate test_ function. "
    "Use pytest.param(..., id='label') to name complex cases. "
    "These rules apply to ALL Python code you write or edit in this session."
)


def is_python_related(prompt: str) -> bool:
    low = prompt.lower()
    return any(kw in low for kw in PYTHON_KEYWORDS)


def main():
    try:
        event = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt: str = event.get("prompt", "")

    # Inject context only for Python-related prompts (reduce noise for other tasks)
    if not is_python_related(prompt):
        sys.exit(0)

    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": STYLE_PRIMER
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
