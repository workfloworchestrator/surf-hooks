---
title: safety-read-only-probes
impact: CRITICAL
tags: safety, read-only, upgrade, probes
---

# Rule: safety-read-only-probes

## The rule

The planner writes a plan and nothing else. It never bumps a pin, regenerates a
lock file, runs a migration, builds an image, or starts a container, and the
plan never gives the upgrade command. It may run, and show, the read-only probes
listed below.

This holds when the user asks you to "just bump it". Deliver the plan, say
plainly that you did not upgrade anything, and point at the upstream docs.

## Why it matters

Many deployments apply the migrations (`db upgrade heads`) when the API starts,
so merely starting a newer image can rewrite the database, and that cannot be
undone without a restore. The planner cannot see which DTAP environment a
command would hit, so a command lifted into the plan is a guess the user may
paste into production.

## How to apply

1. Run or show only these probes:

   | Probe | Where it runs | What it tells you |
   | ----- | ------------- | ----------------- |
   | `grep`, `git log`, `git diff` | the repository | where the code uses an API, setting, or file |
   | the package manager's show or list command for `orchestrator-core` (`uv pip show`, `poetry show` or `pip show`, whichever the project uses) | the API's environment | the installed core version |
   | the deployment's render or config command (for example `docker compose config` or `helm template`) | repository root | the resolved settings and image tags, nothing started |
   | `python main.py db history` | inside the API's environment, in the directory holding `main.py` | the revision chain, with the revision this database is at marked as current |
   | `python main.py db heads` | inside the API's environment, in the directory holding `main.py` | the newest revisions the installed code knows |
   | `npm ls <package>` | inside the UI build | the resolved UI dependency versions |

   The two `db` commands read only. `db upgrade`, `db downgrade`, `db merge`,
   and `db revision` write or generate and are never probes (the `migrate-*`
   commands generate files too).
2. These run against the **installed** release. To see what a hop's migrations
   would be, read the migration files in the target tag on GitHub; do not start
   the target image against the real database to find out.
3. Describe each upgrade step in prose and link the upstream docs.
4. In prose, write "the upgrade", never the command, even to say you did not run
   it. A reader skimming for commands copies whatever is backticked.
5. Pins are the user's to move. The plan names the file and the new value in
   words ("move the `orchestrator-core` pin in the file you found to X.Y.Z"); it
   does not edit the file.

## Examples

Compliant: a read-only probe, and the step described rather than scripted.

```markdown
Check which revision this database is at (marked current in the output):

    <run in the API's environment, in the directory holding main.py>
    python main.py db history

Then move the `orchestrator-core` pin to X.Y.Z, rebuild, and start the API so the migrations apply.
```

Non-compliant: the upgrade itself handed to the user.

```markdown
Run the upgrade:

    python main.py db upgrade heads
```

## Common mistakes

- Running the upgrade because the user asked and the containers were up.
- Editing a dependency pin "to see what breaks".
- Putting a `db upgrade` or build command in the plan "for convenience".
- Naming the upgrade command in prose to say it was not run, instead of writing
  "the upgrade".
- Starting the target image against a real database to preview its migrations.
