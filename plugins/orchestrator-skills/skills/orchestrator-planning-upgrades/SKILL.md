---
name: orchestrator-planning-upgrades
description: >-
  Plans a version-by-version upgrade of orchestrator-core and the wfo-ui
  (orchestrator-ui-components) and scores each release's breaking changes
  against the user's repository, producing UPGRADE_PLAN.md.
  TRIGGER when: planning an orchestrator-core or wfo-ui upgrade, asking what
  breaks between two versions, checking upgrade impact before a release, asked
  to "just bump the version", updating or extending an existing UPGRADE_PLAN.md,
  debugging a plan that missed a breaking change.
  DO NOT TRIGGER when: writing or editing workflows or products, debugging a
  running workflow, upgrading NetBox or other services, reviewing code.
  ALWAYS pass the user's request verbatim as args, versions and any pressure to
  "just do it" included: this skill runs in a forked context and cannot see the
  parent conversation.
context: fork
argument-hint: "[the user's upgrade request, verbatim]"
metadata:
  version: 1.0.0
  author: Nomios
---

# Orchestrator Upgrade Path Planner

## Overview

Produces `UPGRADE_PLAN.md`: the route from the current version to the target for
the upstream dependencies the repository uses, with every breaking change in
that range checked against this repository. A repository may contain only the
API (`core`) or only the UI (`ui`); plan what it contains.

| Dependency | Upstream | Release tags |
| ---------- | -------- | ------------ |
| `core` | `workfloworchestrator/orchestrator-core` | bare: `X.Y.Z` |
| `ui` | `workfloworchestrator/orchestrator-ui-library` | `@orchestrator-ui/orchestrator-ui-components@X.Y.Z` |

Where each one is pinned differs between repositories, so the skill finds that
by searching and never assumes a layout (see Project Context).

**The plan describes how to upgrade; it does not upgrade.** It never bumps a
pin, regenerates a lock file, runs a migration, or builds an image, and it never
hands the user the upgrade command. It may run and show read-only probes. See
[rules/safety-read-only-probes.md](./rules/safety-read-only-probes.md).

`Write` is granted for `UPGRADE_PLAN.md` only. `Bash` is granted for reading
release notes and for the read-only probes.

## Project Context

This skill runs in a forked context, so the user's request arrives verbatim as
the arguments: the versions, the deployment method (Docker Compose, Helm, bare
metal), and anything else the plan depends on. For example:
`/orchestrator-planning-upgrades We run orchestrator-core 4.8.2 and
ui-components 7.5.1 on Docker Compose and want the latest of both.`

Read current versions from the repository, not from the user's memory, by
searching for where each dependency is declared and naming the file you found in
the plan:
- `core`: the `orchestrator-core` requirement and its resolved version in the
  repository's Python dependency and lock files, whichever the project uses:
  `pyproject.toml` with `uv.lock` (uv) or `poetry.lock` (poetry), or
  `requirements*.txt` (pip).
- `ui`: the pin can take several forms, so search the whole repository
  (excluding `node_modules`, `.git` and `.next`) for
  `orchestrator-ui-components`, `orchestrator-ui-library` and
  `example-orchestrator-ui`, in every file type. Forms seen:
  - The `@orchestrator-ui/orchestrator-ui-components` dependency in a
    `package.json` and its lock file.
  - The library built from source at a tag or ref, for example a Dockerfile
    build `ARG` such as
    `REPO_REF=@orchestrator-ui/orchestrator-ui-components@X.Y.Z`. Check whether
    compose files, CI or `.env.example` override that value; the override wins.
  - The
    [example-orchestrator-ui](https://github.com/workfloworchestrator/example-orchestrator-ui)
    app, cloned, forked or vendored at a ref. It pins `ui-components` in its own
    `package.json`, so resolve the components version by reading that file at
    the ref the repository uses, and name both in the plan.
  - Any other file that names the library's version.

If the full-repository search finds no pin for a dependency, do not conclude it
is unused: a missing `package.json` entry is not evidence. Say which searches
you ran and ask the user where it is pinned, or whether it is out of scope (an
API-only repository has no `ui`). If they confirm it is out of scope, plan the
other dependency alone, and skip the pairing and the `## Order` section. Never
guess a pin. A dependency with no target is asked for; a request naming one
dependency plans that dependency only.

## Workflow

1. **Fix the endpoints and the boundaries.** Upstream does not require upgrading
   one minor at a time. Its upgrade guides are per major, plus a few per minor,
   and state only these requirements: be on the previous major first (and on its
   latest minor where the guide says so, as 2.0 does for 1.3.x), read the guides
   for minors a later guide points back to (5.0 points to 4.7 and 4.8), and meet
   the UI/core minimums the guides name. A **boundary** is a major version, a
   version with its own upstream guide, or a UI/core pairing minimum. Everything
   between two boundaries is one hop on either dependency. Every release is
   still read and scored on its own, because breaking notes are stated per
   release. Patches within a minor roll up. Anything the docs do not require,
   such as a soak window or a backup per minor, is written as optional caution,
   never as a requirement.
2. **Enumerate every release in the range, patches included, and read each one's
   notes.** Read
   [rules/sources-enumerate-every-hop.md](./rules/sources-enumerate-every-hop.md)
   before fetching anything. It also says how to find which versions have an
   upstream upgrade guide.
3. **Pair the dependencies**, only when both are in scope. The UI talks to the
   core's API and GraphQL schema. From the release notes, find which UI versions
   a core version needs and the reverse, and state the order to upgrade in. If
   the notes do not say, record that as an `unknown` finding rather than
   assuming.
4. **Inventory the repository.** Find the paths by searching, not by assuming a
   layout. Do not read `.env` files: they hold secrets and may not be visible. A
   setting whose value is not in the committed code or deployment config is
   `unknown`.
   - `core`: the code that imports `orchestrator` (search for `from
     orchestrator` and `import orchestrator`), the repository's own database
     migrations that branch from core's chain, and the `ORCHESTRATOR_*` and
     `OAUTH2_*` settings referenced in code or committed deployment config.
   - `ui`: the dependency pin from Project Context, the Node version the
     repository uses, and the `ORCHESTRATOR_*` settings referenced in committed
     deployment config.
5. **Give every finding a verdict and back it.** Read
   [rules/impact-verdict-needs-evidence.md](./rules/impact-verdict-needs-evidence.md)
   before filling the `Affected` and `Evidence` columns.
6. **Probe, read-only.** Read
   [rules/safety-read-only-probes.md](./rules/safety-read-only-probes.md) before
   running or showing any command, and again if the user asks you to just do the
   upgrade.
7. **Collapse the hops.** On both dependencies, merge consecutive hops that have
   no boundary (step 1) and no action of their own. A pairing minimum orders the
   rollouts; it is not a reason to stop at the release that names it. Then
   re-read the `## Order` list and merge any two consecutive same-dependency
   rollouts with no other-dependency rollout between them whose only separator
   is a patch or a satisfied minimum. Read
   [rules/plan-collapse-hops.md](./rules/plan-collapse-hops.md) before choosing
   the sections.
8. **Write `UPGRADE_PLAN.md`** in the shape below. Each hop's steps are prose:
   follow the upstream guide's own steps for that hop, clear the `before`
   findings, move the pin, rebuild and start so the migrations run, clear the
   `during` and `after` findings. A database backup is a step where an upstream
   guide says so or the hop runs a migration; mark any other precaution
   optional. Link the upstream docs rather than transcribing them:
   - core: <https://workfloworchestrator.org/orchestrator-core/>
   - core releases:
     <https://github.com/workfloworchestrator/orchestrator-core/releases>
   - ui releases:
     <https://github.com/workfloworchestrator/orchestrator-ui-library/releases>

## Plan Format

One `##` section per collapsed hop, dependencies kept separate and each in
ascending order, with the dependency and the section's two versions in the
heading (`## core 4.8 -> 5.0`, `## ui 7.5 -> 8.1`). When both dependencies are
planned, a short `## Order` section above them states which goes first and why.
Each hop carries one findings table with these nine columns, in this order:

| Change | Release | Kind | Severity | When | Affected | Evidence | Action | Source |
| ------ | ------- | ---- | -------- | ---- | -------- | -------- | ------ | ------ |

| Column | Values |
| ------ | ------ |
| `Release` | one version, `X.Y.Z`, never a range |
| `Kind` | `breaking` or `preparation` |
| `Severity` | `critical`, `warning`, or `info` |
| `When` | `before`, `during`, or `after` the hop |
| `Affected` | `yes`, `no`, or `unknown` |

What each value means, and a worked example, are in
[reference.md](./reference.md). Read it before writing the first row.

## Rule Categories

| Category | Prefix | Rules |
| -------- | ------ | ----- |
| Sources | `sources-` | [sources-enumerate-every-hop](./rules/sources-enumerate-every-hop.md) |
| Impact | `impact-` | [impact-verdict-needs-evidence](./rules/impact-verdict-needs-evidence.md) |
| Plan shape | `plan-` | [plan-collapse-hops](./rules/plan-collapse-hops.md) |
| Safety | `safety-` | [safety-read-only-probes](./rules/safety-read-only-probes.md) |

## Supporting References

- [reference.md](./reference.md): column semantics and an example plan. Read at
  step 8.
- [rules/_sections.md](./rules/_sections.md): the rule index.

---

Inspired by
[infrahub-planning-upgrades](https://github.com/opsmill/infrahub-skills) by OpsMill.
