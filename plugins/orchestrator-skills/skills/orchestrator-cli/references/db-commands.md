# Database Commands Reference

Detailed reference for all `python main.py db` commands.

## Migration Architecture

The orchestrator uses Alembic for database migrations with two migration branches:
- **Schema migrations** — DDL changes (tables, columns, indexes)
- **Data migrations** — Product/workflow/resource type registration

## Commands

### `db init`

Initialize the migrations directory structure.

```bash
python main.py db init
```

Creates:
- `migrations/` directory
- `migrations/versions/` and `migrations/versions/schema/`
- Template files: `env.py`, `script.py.mako`, `helpers.py`, `alembic.ini`

Fails if migration directory already exists and is not empty.

### `db upgrade`

Apply pending migrations.

```bash
python main.py db upgrade heads          # Apply all pending migrations (both branches)
python main.py db upgrade <revision>     # Upgrade to specific revision
```

### `db downgrade`

Roll back migrations.

```bash
python main.py db downgrade -1           # Roll back one revision
python main.py db downgrade <revision>   # Downgrade to specific revision
```

### `db heads`

Show current Alembic migration heads. Useful for understanding migration branch state.

```bash
python main.py db heads
```

### `db history`

List migration history in chronological order.

```bash
python main.py db history                # Basic listing
python main.py db history --verbose      # Detailed output
python main.py db history --current      # Mark current revision
```

### `db merge`

Merge multiple Alembic heads when branches have diverged.

```bash
python main.py db merge <rev1> <rev2> --message "merge migration heads"
```

### `db revision`

Create a new manual migration revision.

```bash
python main.py db revision --message "add custom index"
python main.py db revision --message "auto changes" --autogenerate
python main.py db revision --message "data change" --head data@head
```

Options:
- `--message` / `-m` — Revision description
- `--version-path` — Specific path for version file
- `--autogenerate` — Auto-detect schema changes
- `--head` — Which branch head to extend (default: `data@head`)

### `db migrate-domain-models`

Auto-detect and generate migrations for domain model changes. This is the primary command for evolving product block schemas.

```bash
python main.py db migrate-domain-models "add bandwidth field to port"
python main.py db migrate-domain-models "rename node_name to hostname" --test
python main.py db migrate-domain-models "add vlan block" --inputs '{"new_resource_types": {"vlan_id": "int"}}'
```

Options:
- `--test` — Preview changes without generating migration file
- `--inputs TEXT` — Pre-fill interactive prompts (JSON string)
- `--updates TEXT` — Pre-fill update prompts (JSON string)
- `--confirm-warnings` — Accept all warning prompts automatically

**Detects automatically**:
- New domain model attributes/resource types
- Renamed attributes/resource types
- Removed attributes/resource types
- New or removed domain models

**Always back up the database before running this command.**

### `db migrate-workflows`

Register new workflows and detect changes between code and database.

```bash
python main.py db migrate-workflows "add service port workflows"
python main.py db migrate-workflows "update workflow targets" --test
```

Options:
- `--test` — Preview without generating migration

Compares registered `LazyWorkflowInstance` entries against the database and generates a migration for differences.

### `db migrate-tasks`

Register task workflows (scheduled/background tasks).

```bash
python main.py db migrate-tasks "add cleanup task"
python main.py db migrate-tasks "register tasks" --test
```

Options:
- `--test` — Preview without generating migration

## Typical Migration Workflows

### Adding a New Product (from scratch)

```bash
# 1. Generate the product migration from YAML config
python main.py generate migration --config-file config.yaml

# 2. Apply migrations
python main.py db upgrade heads

# 3. Register workflows
python main.py db migrate-workflows "add new product workflows"

# 4. Apply workflow migration
python main.py db upgrade heads
```

### Adding a Field to an Existing Product Block

```bash
# 1. Update the Python domain model (add the field)
# 2. Auto-detect and generate migration
python main.py db migrate-domain-models "add bandwidth to port block" --test
# 3. Review the test output, then generate for real
python main.py db migrate-domain-models "add bandwidth to port block"
# 4. Apply
python main.py db upgrade heads
```

### Renaming a Field

```bash
# 1. Update the Python domain model
# 2. Generate migration (will prompt for rename confirmation)
python main.py db migrate-domain-models "rename node_name to hostname"
# 3. Apply
python main.py db upgrade heads
```

### Resolving Multiple Heads

```bash
# Check current state
python main.py db heads
# Merge diverged branches
python main.py db merge <rev1> <rev2> -m "merge heads"
# Apply
python main.py db upgrade heads
```
