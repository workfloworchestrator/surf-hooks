---
title: impact-verdict-needs-evidence
impact: CRITICAL
tags: impact, evidence, verdict, affected
---

# Rule: impact-verdict-needs-evidence

## The rule

Every finding gets an `Affected` verdict of `yes`, `no`, or `unknown`. A `yes`
or `no` names the artifact that proves it. An `unknown` names the probe that
would settle it.

## Why it matters

A generic list of breaking changes is the release notes again, and the user
already has those. The value of the plan is the verdict: which of these changes
hit this repository. "May apply to your setup" hands the work back, and a `yes`
with nothing behind it cannot be checked, so the user cannot tell a real blocker
from a guess before the upgrade starts.

## How to apply

1. Check each change against the repository inventory from step 4.
2. For `yes` or `no`, put something locatable in `Evidence`, strongest first:
   - a file path with the element: `<app dir>/workflows/foo.py -> from
     orchestrator.services import x`
   - a migration revision: `<migrations dir>/versions/<rev>.py`
   - a pinned version or setting: `pyproject.toml -> orchestrator-core =
     "4.8.2"`
   - a search and its result: ``grep -rn 'old_fn' <app dir>` returns nothing``
3. Use `unknown` when the evidence is not in hand, for example code the user did
   not share. Then the `Action` names the probe that would decide it: a `grep`
   over named paths, a named file to read, or a read-only probe from
   [safety-read-only-probes](./safety-read-only-probes.md). Lead with the probe,
   then the remedy: "if OAuth2 is configured, do X" leaves the user unable to
   tell whether it is, so say where to look first. Name the place by name (the
   compose file, the Helm values file, `package.json`), not "your deployment
   file". `unknown` with a probe is honest; a guessed `yes` or `no` is not.
4. A change that reaches every deployment, such as a core database migration,
   still needs evidence for `yes`: the migration file in the release against
   this database's `db history` (current marker) and `db heads` output. "The
   release applies it everywhere" is the release note again, not evidence.
   Without a probe it is `unknown`, with that probe as the `Action`. The
   repository's own migrations that branch from core's chain are evidence for a
   `yes` on any core migration change.
5. Write the bare value. The column holds `yes`, `no`, or `unknown`, not a
   sentence.
6. Make each row stand on its own. "Same as the row above" leaves this row with
   no evidence of its own, and rows get read, sorted, and copied one at a time.
7. A change that touches nothing in the repository, such as a UI feature this
   deployment never renders, either gets a runnable search naming the place or
   is not a finding: put it in the hop's steps as a note.

## Examples

Compliant: a decided verdict with its artifact, and an undecided one with its
probe.

```markdown
| Change | Release | Kind | Severity | When | Affected | Evidence | Action | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `old_fn` removed | 5.0.0 | breaking | critical | before | yes | `<app dir>/workflows/foo.py -> old_fn(...)` | Replace with `new_fn` | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/5.0.0 |
| Node 20 dropped | 8.0.0 | breaking | critical | before | unknown | `package.json` `engines` allows Node 20; the new minimum was not stated in the notes | Read the `engines` field in the target's `package.json` at its tag | https://github.com/workfloworchestrator/orchestrator-ui-library/releases |
```

Non-compliant: evidence that restates the finding, and a verdict that is not
one.

```markdown
| Change | Release | Kind | Severity | When | Affected | Evidence | Action | Source |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `old_fn` removed | 5.0.0 | breaking | critical | before | yes | Your workflows use the removed function | Update them | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/5.0.0 |
| Settings renamed | 5.0.0 | breaking | warning | before | may apply | | Review your config | https://github.com/workfloworchestrator/orchestrator-core/releases/tag/5.0.0 |
```

## Common mistakes

- Evidence that repeats the change in other words.
- `unknown` with an `Action` of "review" or "check", which names no probe.
- `unknown` with an `Action` that starts "if you use X", which names the
  condition but not how to test it.
- Leaving `Affected` blank for a change that does not apply. That is a `no`,
  with the evidence that it does not apply.
- Advice with no evidence, such as a backup reminder, marked `yes`. General
  preparation is prose in the hop steps, not a finding.
