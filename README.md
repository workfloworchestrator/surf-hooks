 # SURF-Hooks a.k.a Save the Baby Seals

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
```

---

### `orchestrator-skills`

Skills for developing with [orchestrator-core](https://github.com/workfloworchestrator/orchestrator-core):
CLI scaffolding, workflow creation, domain models, and product lifecycle management.

This plugin provides two skills:

#### `orchestrator-workflows`

Covers everything needed to write orchestrator-core workflows: the generator DSL,
input forms, step types, domain model lifecycle, state injection, and workflow registration.

Activates when you ask to:
- Create, modify, or terminate a workflow
- Define an input form or add a workflow step
- Use `FormGenerator`, `FormPage`, `StepList`, `inputstep`, `retrystep`, or callbacks
- Understand domain models, product blocks, or subscription lifecycle
- Implement business logic in generated workflow scaffolding

Key topics covered:
- Workflow decorators: `@create_workflow`, `@modify_workflow`, `@terminate_workflow`, `@validate_workflow`, `@task`
- Step types: `@step`, `@retrystep`, `@inputstep`, `callback_step`, `step_group`, `conditional`
- Multi-page input forms with dynamic dropdowns and validators
- Domain model lifecycle variants (INITIAL → PROVISIONING → ACTIVE → TERMINATED)
- State injection and the rule that domain models must be returned in state to persist
- Registering workflows via `LazyWorkflowInstance` and database migrations

#### `orchestrator-cli`

Covers the `python main.py` CLI that scaffolds products, workflows, domain models,
migrations, and tests from YAML configuration files.

Activates when you ask to:
- Generate a product, scaffold a workflow, or create product blocks
- Run or manage database migrations
- Use CLI commands like `generate`, `db`, or `scheduler`
- Create a new product type from scratch using a YAML config file

Key topics covered:
- End-to-end scaffolding sequence: product-blocks → products → workflows → unit-tests → migration
- YAML configuration format for products, fields, lifecycle requirements, and workflow types
- `generate` command flags: `--dryrun`, `--force`, `--config-file`, `--folder-prefix`
- Database commands: `db upgrade`, `db migrate-workflows`, `db migrate-domain-models`
- Scheduler commands: `scheduler run`, `scheduler show-schedule`, `scheduler force`
- Custom Jinja2 templates for extending generated workflow scaffolding

---
Installation

Add the marketplace

/plugin marketplace add workfloworchestrator/surf-hooks

Install a plugin

/plugin install surf-python-style@surf-hooks
/plugin install orchestrator-skills@surf-hooks

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
/plugin reload orchestrator-skills

---
Publishing changes

1. Edit the plugin or add new ones under plugins/
2. Bump version in .claude-plugin/marketplace.json
3. Commit and push to main — the marketplace is live immediately

---
License

MIT