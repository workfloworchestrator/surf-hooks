---
title: plan-collapse-hops
impact: HIGH
tags: hops, boundaries, deploy-steps, plan-shape
---

# Rule: plan-collapse-hops

## The rule

Read and score every release on its own, then group consecutive releases into
one hop on both dependencies, ending a hop only at a **boundary** that upstream
documents. Upstream does not require upgrading one minor at a time, so a release
is not a hop of its own unless it is a boundary or carries an action.

Boundaries, each taken from upstream's own guides:

1. **Major version.** The guides are per major (`guides/upgrading/5.0/` covers
   4.x to 5.0) and say to be on the previous major first. 2.0 also says to be on
   the latest 1.3.x before starting.
2. **A version with its own upstream upgrade guide.** Later guides point back to
   these (the 5.0 guide sends scheduled-task and workflow-authorization-callback
   users to the 4.7 and 4.8 guides first), and each can carry steps of its own.
3. **A pairing minimum.** A guide names the other dependency's version it needs
   (core 5.0 wants UI components 8.1 or newer; UI 9.0 needs core 5.4 or newer).
   The minimum constrains only the order, in two directions, and neither makes
   the version that carries it a hop of its own:
   - The **dependency that must move first** ends its hop at the required
     version (core stops at 5.4 so UI 9.0 can follow).
   - The **dependent** may start its next hop only once that version is
     deployed, and ends it before the next release whose minimum is not yet met
     (UI stops before 10.3 until core is at 5.6).
   A dependent release with a minimum but no guide and no action (UI 9.0.1
   needing core 5.5) joins the next hop on the dependent's side, deployed after
   the core hop that satisfies it. Test: if the earlier rollout step already put
   the other dependency at the minimum, the release needs no separate rollout.
4. **Action boundary.** The release has a finding with `Affected` of `yes` or
   `unknown` and a `before` or `during` action, or a decision for the user (for
   example a version that needs an unreleased core). Give it its own section.

Do not invent others. A backup per minor, a soak window or a rollback point per
minor is the planner's caution, not an upstream requirement: write it as
optional, and write a backup as required only where a guide says so or the hop
applies a migration (many deployments run them when the API starts, so check
where this one does).

## Why it matters

A plan that makes the user stop at every minor sends them through rebuilds and
smoke tests the docs never ask for, and passes the planner's habit off as
upstream's rule. A plan that merges across a documented boundary skips a guide
the user was told to read.

## How to apply

Scoring stays per release (see
[sources-enumerate-every-hop](./sources-enumerate-every-hop.md), which also says
how to find the guides). Walk each dependency in ascending order and merge
release N into the open hop unless N is a boundary above.

A merged section is headed with the whole range (`## core 5.0 -> 5.4`, `## ui
7.5 -> 8.1`), gives one set of steps targeting the last version, and holds one
findings table with every surviving row, each still stamped with its single
`Release`. Releases passed over with nothing affecting the repository get one
prose line naming what they changed, not a row and not a section.

State the fallback in the merged section: if the combined step fails, bisect
through the intermediate releases to find the one that broke it.

## Examples

Compliant: core 5.1 to 5.3 have no guide, pairing minimum or action, so they
join the 5.4 hop, which is a boundary because it has its own guide.

```markdown
## core 5.0 -> 5.4

Steps: follow the 5.4 upgrade guide, move the pin to
5.4.x, rebuild and start so the migrations run. Bisect
through 5.1.x to 5.3.x if it fails.

Passed over without findings: 5.1.0 adds X; 5.2.0 adds Y.
```

Non-compliant: a section per minor, each reading "No findings", or "never merge
core hops" given as if upstream required it.

```markdown
## core 5.1 -> 5.2
No findings.

## core 5.2 -> 5.3
No findings.
```

## Common mistakes

- Merging across a major or across a version that has its own guide.
- Making a release its own rollout because it names a pairing minimum. The
  minimum orders the rollouts; it does not require a rollout at that release (UI
  9.0.1 merges into 9.0 -> 10.0, not "9.0 -> 9.0.1" then "9.0.1 -> 10.0").
- Dropping a pairing boundary because the hop looked quiet: check the pairing
  table in the Order section first.
- Presenting a backup or soak window as an upstream requirement.
- Merging a hop whose only finding is `Affected: no` with one whose finding is
  `yes`: the `yes` hop keeps its own section.
- Deleting the findings from a merged hop. Rows stay; only the empty sections
  go.
