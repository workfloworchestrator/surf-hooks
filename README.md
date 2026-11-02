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

### `surf-shunt`

Saves Claude tokens by shunting I/O-heavy work to an on-prem model (default
`Qwen3.8-27B-FP8`) behind an OpenAI-compatible LiteLLM proxy. There is no built-in
proxy URL: point it at your own via the variables below.
Modelled on Spotify's `shunt` plugin, which does the same via AiKA.

Three layers:

1. **Hook** (`PreToolUse` on `Read|Bash`) blocks full reads of files over 350 lines
   (`Read` without offset/limit, `cat`/`less`/`more`/`bat`) and tells Claude the exact
   `bulk-read` command to run instead. Targeted reads (offset/limit, `head`, `tail`,
   `sed -n`, output piped or redirected to a file) pass through. Each segment of a
   compound command is checked on its own, so `cat big.py; git diff | head` still blocks.
2. **Script** `scripts/shunt.py` (stdlib only) sends the files to the model and prints only the answer:
   - `bulk-read --question "..." --paths a.py b.py` — the files never enter Claude's context
   - `code-write --spec "..." --reference ref.py --target out.py` — generates boilerplate straight to disk
3. **Skills** `bulk-reader` and `code-writer` tell Claude when to use each.

Both scripts need Python 3.10 or newer. The hook and skills start them through
`scripts/run-python`, which uses the first `python3`, `python3.14` … `python3.10` on
PATH that is new enough (a stock macOS `python3` is 3.9). Without one it logs a
warning to `surf-shunt.log` in the plugin data directory; the hook then shows the
warning and lets tool calls through instead of blocking them.

Content is meant to stay on-prem: requests set `disable_fallbacks`, and an answer
from any model other than the one requested is discarded. A failed call errors
out instead of falling back to a cloud model.

#### Configuration

Set these in the `env` block of `.claude/settings.json`. Set `SURF_SHUNT_BASE_URL`
and `SURF_SHUNT_API_KEY` together, or neither to reuse the `ANTHROPIC_BASE_URL` +
`ANTHROPIC_AUTH_TOKEN` pair Claude Code already uses (when Claude Code itself runs
through the proxy). A URL and key are never mixed across sources.

| Variable | Default | Purpose |
|----------|---------|---------|
| `SURF_SHUNT_MODEL` | `Qwen3.8-27B-FP8` | Worker model for both roles |
| `SURF_SHUNT_READ_MODEL` / `SURF_SHUNT_WRITE_MODEL` | — | Per-role override |
| `SURF_SHUNT_BASE_URL` | `$ANTHROPIC_BASE_URL` | LiteLLM proxy URL |
| `SURF_SHUNT_API_KEY` | `$ANTHROPIC_AUTH_TOKEN` | LiteLLM key |
| `SURF_SHUNT_MIN_LINES` | `350` | Hook threshold |
| `SURF_SHUNT_DISABLE` | — | `1` turns the hook off (e.g. while the model is down) |
| `SURF_SHUNT_TIMEOUT` | `300` | Seconds per call |
| `SURF_SHUNT_MAX_INPUT_TOKENS` | ¾ of the model's window | Refuse larger requests (see below) |

#### Per-model limits

The input limit is set automatically from the model each call uses, so with
`SURF_SHUNT_READ_MODEL` and `SURF_SHUNT_WRITE_MODEL` pointing at different models,
reads and writes each get their own limit. Requests over the limit are refused
before anything is sent. The context windows live in `MODEL_CONTEXT_TOKENS` in
`scripts/shunt.py`, measured against the SURF proxy on 2026-11-02 (the proxy does
not publish them):

| Model | Context window | Default input limit |
|-------|----------------|---------------------|
| `Qwen3.8-27B-FP8` (default) | 262,144 | 196,608 |
| `gpt-oss-120b` | 131,072 | 98,304 |
| anything else | 131,072 (assumed) | 98,304 |

Only three quarters of the window goes to input; the answer shares the window.
`SURF_SHUNT_MAX_INPUT_TOKENS` overrides the limit for every model.

Request size is estimated the way the tokenizer splits text (words, single digits,
punctuation runs), calibrated against `Qwen3.8-27B-FP8`: within about 5% for Python,
Markdown and lockfiles. A flat four-characters-per-token estimate is fine for code
but undercounts lockfile hashes 2.6x, which let a 558 KB `uv.lock` through to fail
at the proxy. Over-limit requests are now refused up front with advice to split the
file or grep it. When the proxy does reject a request, the error includes the
estimated size, because LiteLLM hides the backend's context-length message.

To add a model, add its context window to `MODEL_CONTEXT_TOKENS`. The proxy hides
backend errors, so measure the window by sending `"hello " * n` prompts of growing
`n` with `max_tokens: 1` and finding where requests start to fail.

Run its tests with `python3 -m pytest plugins/surf-shunt`.

---
Installation

Add the marketplace

/plugin marketplace add workfloworchestrator/surf-hooks

Install a plugin

/plugin install surf-python-style@surf-hooks
/plugin install orchestrator-skills@surf-hooks
/plugin install surf-shunt@surf-hooks

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