 # surf-hooks

Claude Code hooks and plugins maintained by [workfloworchestrator](https://github.com/workfloworchestrator).
Also known internally as **save-the-baby-seals** 🦭.

---

## Plugins

### `surf-python-style` (alias: `save-the-baby-seals`)

A PostToolUse hook that enforces SURF Python style conventions on every file
Claude writes or edits. It parses the AST and nudges — or hard-blocks — Claude
when style violations are detected.

#### What it enforces

| Rule | Behaviour |
|------|-----------|
| `break` / `continue` inside `for` loops | Soft nudge: suggests `itertools.takewhile`, `filter()`, or early `return` in a helper |
| Nested `for` loops beyond depth 1 | Soft nudge: suggests `itertools.product()`, `chain.from_iterable()`, or a helper function |
| Nested `for` loops at depth ≥ 3 | **Hard block** (exit code 2): Claude must refactor before proceeding |

The hook does **not** check `while` loops or code outside `for` constructs.

#### Configuration

Open `plugins/surf-python-style/hooks/scripts/python_style_hook.py` and edit the
constants near the top:

```python
MAX_NESTING_DEPTH = 1      # Nudge threshold (default: 1)
HARD_BLOCK_DEPTH  = 3      # Hard-block threshold (default: 3)
HARD_BLOCK_BREAKS = False  # Set True to hard-block break/continue instead of nudging

---
Installation

Add the marketplace

/plugin marketplace add workfloworchestrator/surf-hooks

Install the plugin

/plugin install surf-python-style@surf-hooks

Or using the alias:

/plugin install save-the-baby-seals@surf-hooks

---
Local development

Clone

git clone git@github.com:workfloworchestrator/surf-hooks.git
cd surf-hooks

Test the hook manually

echo '{"tool_input":{"file_path":"example.py","new_content":"for x in a:\n  for y in b:\n    pass"}}' \
  | python plugins/surf-python-style/hooks/scripts/python_style_hook.py

Run the test suite

pytest plugins/surf-python-style/hooks/scripts/

Load the plugin locally in Claude Code

/plugin marketplace add ./path/to/surf-hooks
/plugin install surf-python-style@surf-hooks

---
Updating

git pull origin main

Claude Code will pick up the latest version on the next session, or reload with:

/plugin reload surf-python-style

---
Publishing changes

1. Edit the plugin or add new ones under plugins/
2. Bump version in .claude-plugin/marketplace.json
3. Commit and push to main — the marketplace is live immediately

---
License

MIT