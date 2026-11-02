---
name: bulk-reader
description: "Delegate bulk file reading to the on-prem model (Qwen3.8-27B-FP8 by default). Use when you need to read files >350 lines, answer questions across 3+ files, or summarize large diffs. Not for debugging or for code you are about to edit."
---

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/run-python ${CLAUDE_PLUGIN_ROOT}/scripts/shunt.py bulk-read --question "<question>" --paths <file1> [<file2> ...]
```

The files go to the on-prem model, never into your context — only the answer comes back.

- Each call is independent. For a follow-up, ask again with the same `--paths`; re-sending files costs you nothing.
- To summarize a diff, write it to a file first (`git diff main > /tmp/changes.diff`) and pass that path.
- Ask specific questions ("which functions call `get_db`?") rather than "summarize this file".
- Verify line numbers and exact values with a targeted Read (offset/limit) before using them in an edit.
- If the call fails (model unavailable, request too large), tell the user and fall back to targeted reads.
  Never retry against a different model: the point is that the content stays on-prem.
