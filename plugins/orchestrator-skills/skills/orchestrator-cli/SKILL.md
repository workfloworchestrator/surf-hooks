---
name: orchestrator-cli
description: "This skill should be used when the user asks to \"generate a product\", \"scaffold a workflow\", \"create product blocks\", \"run database migrations\", \"migrate workflows\", \"migrate domain models\", \"generate unit tests\", \"generate a migration\", \"use the orchestrator CLI\", or mentions orchestrator-core CLI commands like generate, db, or scheduler. Also use when the user wants to create a new product type from scratch, needs help with YAML configuration files for the generator, or asks about orchestrator-core project setup and scaffolding."
---

# Orchestrator-Core CLI

The orchestrator-core CLI (`python main.py`) scaffolds products, workflows, domain models, migrations, and tests from YAML configuration files. It also manages database migrations and the scheduler.

## Command Overview

| Command | Purpose |
|---------|---------|
| `generate product-blocks` | Generate product block domain models |
| `generate products` | Generate product type domain models |
| `generate workflows` | Generate create/modify/terminate/validate workflows |
| `generate unit-tests` | Generate pytest test files |
| `generate migration` | Generate Alembic data migration |
| `db upgrade` | Run database migrations |
| `db migrate-workflows` | Register workflows in database |
| `db migrate-domain-models` | Generate migration for domain model changes |
| `db migrate-tasks` | Register task workflows in database |
| `scheduler run` | Start the scheduler |
| `scheduler show-schedule` | List scheduled jobs |

## End-to-End Scaffolding Workflow

To scaffold a complete new product with workflows, follow this exact sequence.

### Step 1: Write the YAML Configuration

Create a YAML config file describing the product. Read `references/generate-config.md` for the full format specification, field types, and examples.

Minimal example:

```yaml
config:
  summary_forms: false
name: service_port
type: ServicePort
tag: SP
description: "A network service port"
product_blocks:
  - name: service_port
    type: ServicePort
    tag: SP
    description: "service port block"
    fields:
      - name: port_name
        type: str
        description: "Name of the port"
        required: provisioning
        modifiable:
      - name: port_speed
        type: int
        description: "Speed in Gbps"
        required: active
workflows:
  - name: create
  - name: modify
  - name: terminate
  - name: validate
```

### Step 2: Generate in Order

Generation order matters — product blocks first, then products, then workflows:

```bash
# 1. Preview first (dryrun is default)
python main.py generate product-blocks --config-file config.yaml

# 2. Generate for real
python main.py generate product-blocks --config-file config.yaml --no-dryrun --force
python main.py generate products --config-file config.yaml --no-dryrun --force
python main.py generate workflows --config-file config.yaml --no-dryrun --force
python main.py generate unit-tests --config-file config.yaml --no-dryrun --force

# 3. Generate the database migration
python main.py generate migration --config-file config.yaml
```

### Step 3: Run Migrations and Register Workflows

```bash
python main.py db upgrade heads
python main.py db migrate-workflows "add service port workflows"
```

### Step 4: Implement Business Logic

Generated workflows contain TODO placeholders. Fill in:
- External system provisioning in create workflows
- Modification logic in modify workflows
- Cleanup/deprovisioning in terminate workflows
- Validation checks in validate workflows

## Generate Commands — Quick Reference

All generate commands share these flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--config-file` / `-cf` | required | Path to YAML config |
| `--dryrun` / `--no-dryrun` | `--dryrun` | Preview without writing files |
| `--force` / `-f` | `False` | Overwrite existing files |
| `--python-version` / `-p` | `3.11` | Python version for generated code |
| `--folder-prefix` / `-fp` | `""` | Output directory prefix |

Additional flags:
- `generate workflows`: `--tdd` (default: True), `--custom-templates` / `-ct`
- `generate migration`: `--skip-existing-blocks`

## Database Commands

Read `references/db-commands.md` for detailed command syntax and migration workflows.

Key commands:

```bash
# Schema migrations
python main.py db upgrade heads          # Apply all pending migrations
python main.py db downgrade -1           # Roll back one migration
python main.py db heads                  # Show current migration heads
python main.py db history --verbose      # Show migration history

# Domain model migrations (auto-detects changes)
python main.py db migrate-domain-models "description of changes"
python main.py db migrate-domain-models "description" --test  # Preview only

# Workflow registration
python main.py db migrate-workflows "description"
python main.py db migrate-tasks "description"
```

**Important**: Always back up the database before running `migrate-domain-models`, `migrate-workflows`, or `migrate-tasks`.

## Scheduler Commands

```bash
python main.py scheduler run                    # Start scheduler (foreground)
python main.py scheduler show-schedule          # List all scheduled jobs
python main.py scheduler force <TASK_ID>        # Force-execute a specific task
python main.py scheduler load-initial-schedule  # Load default schedules
```

## Generated File Locations

| Command | Output Location |
|---------|----------------|
| `generate product-blocks` | `products/product_blocks/<name>.py` |
| `generate products` | `products/product_types/<name>.py` |
| `generate workflows` | `workflows/<name>/create_<name>.py`, `modify_<name>.py`, etc. |
| `generate unit-tests` | `test/unit_tests/products/` and `test/unit_tests/workflows/` |
| `generate migration` | `migrations/versions/schema/` |

All paths are relative to `--folder-prefix` (defaults to project root).

## Custom Templates

Extend generated workflows with custom Jinja2 templates via `--custom-templates`:

- `additional_create_imports.j2`, `additional_create_input_fields.j2`, `additional_create_steps.j2`
- `additional_modify_imports.j2`, `additional_modify_input_fields.j2`, `additional_modify_steps.j2`
- `additional_terminate_imports.j2`, `additional_terminate_input_fields.j2`, `additional_terminate_steps.j2`

## Common Issues

- **"file already exists"**: Use `--force` to overwrite existing files.
- **Workflow not in API**: Register with `python main.py db migrate-workflows "message"`.
- **Multiple migration heads**: Merge with `python main.py db merge <rev1> <rev2> -m "merge"`.
- **LazyWorkflowInstance missing**: `workflows/__init__.py` only updates with `--force`.

## Reference Files

- **`references/generate-config.md`** — Complete YAML configuration format: all fields, types, constraints, fixed inputs, enums, validations, and worked examples
- **`references/db-commands.md`** — Detailed database command reference with all options and migration workflows
