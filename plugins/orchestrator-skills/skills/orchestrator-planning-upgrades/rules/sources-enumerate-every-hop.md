---
title: sources-enumerate-every-hop
impact: CRITICAL
tags: release-notes, breaking-changes, curl, patch-releases
---

# Rule: sources-enumerate-every-hop

## The rule

Read the notes of **every** stable release between the current version and the
target, for each dependency, patches included, and attribute each finding to the
one release that introduced it.

Reading every patch is not installing every patch. A hop to X.Y.3 applies what
X.Y.1 through X.Y.3 changed in one go, so their breaking changes all land in
that hop.

## Why it matters

A plan built from the target release's notes alone misses what the releases in
between broke, and the upgrade then fails on a change the plan never named.
Patch releases carry breaking changes too, and no machine-readable flag marks
them.

## How to apply

1. List the releases. `gh` may not be installed, so use the GitHub API with
   `curl` and `jq`; the list comes newest first by date, so sort by version
   before walking the range. Page through every release (`&page=2`, `&page=3`,
   ...) until a page is empty rather than trusting one page of 100.

   `core`: bare tags, drop prereleases (`a`, `b`, `rc`):

   ```bash
   curl -s 'https://api.github.com/repos/workfloworchestrator/orchestrator-core/releases?per_page=100' \
     | jq -r '.[] | select(.prerelease | not) | .tag_name'
   ```

   `ui`: the repository also tags other packages, so keep only the components
   tags:

   ```bash
   curl -s 'https://api.github.com/repos/workfloworchestrator/orchestrator-ui-library/releases?per_page=100' \
     | jq -r '.[] | select(.prerelease | not) | .tag_name | select(startswith("@orchestrator-ui/orchestrator-ui-components@"))'
   ```

   With `gh` installed, `gh api --paginate` with the same `--jq` filter is
   equivalent.
2. Find the upstream upgrade guides, since each one is a hop boundary (see
   [plan-collapse-hops](./plan-collapse-hops.md)). The guides index page is not
   served, so fetch any one guide and read its navigation, which lists them all:
   `https://workfloworchestrator.org/orchestrator-core/guides/upgrading/4.0/`
   (core guides and UI library guides both appear). Do not hard-code the list:
   it grows with each release. Read every guide whose version falls in the
   range, and read the prerequisites of each; link the guide as the row's
   `Source`.
3. Read each release in the range, from the one after the current version up to
   and including the target:

   ```bash
   curl -s 'https://api.github.com/repos/workfloworchestrator/orchestrator-core/releases/tags/X.Y.Z' | jq -r .body
   ```

   Encode `@` and `/` in UI tags (`%40`, `%2F`).
4. **Read the prose; do not parse for a flag.** Bodies are mostly auto-generated
   PR lists (`## What's Changed`), so breaking changes hide in PR titles
   (`feat!:`, "remove", "rename", "drop support"), in dependency bumps (Python,
   Node, SQLAlchemy, Pydantic, Next.js, React), and in linked migration or
   upgrade guides. Open those PRs and guides when a title suggests a break. Skim
   dependency chores that change nothing the repository imports.
5. Stamp each row's `Release` with the single version that introduced the
   change, and name the change itself. A release with nothing breaking needs no
   row.
6. Put the `Source` link to that release's notes, or to the PR or guide they
   link to.

## Examples

Compliant: each change named, each row one release.

```markdown
| Change | Release | ... |
| --- | --- | --- |
| Python 3.11 support dropped | X.Y.0 | ... |
| Search endpoint date comparison fixed | X.Y.3 | ... |
```

Non-compliant: a range standing in for changes nobody read.

```markdown
| Change | Release | ... |
| --- | --- | --- |
| Review intermediate release notes | X.Y.Z-A.B.C | ... |
```

## Common mistakes

- Reading only the target because the user asked what is new in it.
- Reading only `X.Y.0` releases and skipping patches.
- Treating a release with no "Breaking changes" heading as safe.
- Letting prereleases or non-components UI tags into the range.
- Stopping at the first page of the API listing.
