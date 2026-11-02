---
name: code-writer
description: "Delegate boilerplate code generation to the on-prem model (Qwen3.8-27B-FP8 by default). Use for tests, config, docstrings, type stubs, or any generation where >80% is predictable from reference files."
---

```bash
# Generate and write directly to the target file
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/shunt.py code-write --spec "<what to generate>" --reference <ref-file> [<ref-file> ...] --target <output-path>

# Print to stdout instead (omit --target)
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/shunt.py code-write --spec "<what to generate>" --reference <ref-file>
```

- `--reference` is required: pass the file(s) whose patterns the output must follow, plus the code under test when generating tests.
- An existing `--target` is never overwritten unless you pass `--force`.
- Each call is independent. To build on what was just generated, pass that file as a `--reference` for the next call.
- Review the output and make surgical edits for the part that needs real judgment. Run the tests/linters before reporting success.
- If the call fails (model unavailable, request too large), tell the user rather than retrying against another model.
