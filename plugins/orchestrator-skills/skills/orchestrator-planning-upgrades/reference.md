# Upgrade Plan Reference

## Columns

| Column | Holds |
| ------ | ----- |
| `Change` | The change, named: what the release did, not "review the notes" |
| `Release` | The single version that introduced it, `X.Y.Z` |
| `Kind` | `breaking` when something stops working; `preparation` when the release asks for work that is not a breakage, such as moving a dependency or Node version alongside it |
| `Severity` | `critical`: the API or UI fails to build or start, or the migrations fail, until it is fixed. `warning`: the upgrade completes but a workflow, product, API client, or UI page the user relies on breaks. `info`: worth knowing, nothing to fix |
| `When` | `before` the hop (code or config that must change first), `during` it (a migration or dependency that moves alongside), or `after` it (follow-up cleanup, deprecations) |
| `Affected` | `yes`, `no`, or `unknown`; see [impact-verdict-needs-evidence](./rules/impact-verdict-needs-evidence.md) |
| `Evidence` | The artifact behind a `yes` or `no` |
| `Action` | What the user does, in the imperative; for `unknown`, the probe that settles it |
| `Source` | The release note, or the migration guide it links to |

## Example

The shape to follow. The rows are **illustrative**: the changes and the
placeholder versions (`A.B`, `C.D.E`) are made up to show the format, so never
copy them into a plan or treat them as real releases. Every real row comes from
reading the notes for its range.

```markdown
# Upgrade plan: orchestrator-core CURRENT to TARGET

Nothing was upgraded. Each step below is for you to run.

## Order

Upgrade `core` first: the UI in use states no minimum core version.

## core A.B -> C.D

Steps:

1. Back up the database.
2. Clear the `before` findings below.
3. Move the `orchestrator-core` pin to C.D.E, rebuild, and start the API so the migrations run.
4. Clear the `during` and `after` findings.

| Change | Release | Kind | Severity | When | Affected | Evidence | Action | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `old_helper` removed from `orchestrator.services` | C.D.E | breaking | critical | before | yes | `<app dir>/workflows/foo.py -> from orchestrator.services import old_helper` | Switch the import to `new_helper` | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/C.D.E |
| `OAUTH2_SOME_SETTING` renamed | C.D.E | breaking | warning | before | no | `grep -rn 'OAUTH2_SOME_SETTING' <app dir> <deployment config dir>` returns nothing | None | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/C.D.E |
| `old_fn` deprecated | C.D.E | preparation | info | after | unknown | Workflows under `workflows/` were not shared | `grep -rn 'old_fn' <app dir>` | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/C.D.E |
```
