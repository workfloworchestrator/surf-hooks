/**
 * Unit tests for the pure helpers in hooks.ts.
 * Run with: node --experimental-strip-types --test .opencode/lib/hooks.test.ts
 */

import { test } from "node:test"
import assert from "node:assert/strict"
import {
  isEditTool,
  isReadTool,
  toClaudeEvent,
  patchEvents,
  resultText,
  withResultText,
  appendResultText,
  parseHookStdout,
} from "./hooks.ts"

test("tool classification", () => {
  assert.ok(isEditTool("edit") && isEditTool("write") && isEditTool("patch"))
  assert.ok(!isEditTool("read") && !isEditTool("shell"))
  assert.ok(isReadTool("read") && isReadTool("shell"))
  assert.ok(!isReadTool("edit"))
})

test("read maps path/offset/limit", () => {
  assert.deepEqual(toClaudeEvent("read", { path: "a.py" }, "/w"), {
    tool_name: "Read",
    tool_input: { file_path: "a.py" },
    cwd: "/w",
  })
  assert.deepEqual(toClaudeEvent("read", { path: "a.py", offset: 10, limit: 5 }, "/w"), {
    tool_name: "Read",
    tool_input: { file_path: "a.py", offset: 10, limit: 5 },
    cwd: "/w",
  })
  assert.equal(toClaudeEvent("read", {}, "/w"), null)
})

test("shell maps command", () => {
  assert.deepEqual(toClaudeEvent("shell", { command: "cat big.py" }, "/w"), {
    tool_name: "Bash",
    tool_input: { command: "cat big.py" },
    cwd: "/w",
  })
  assert.equal(toClaudeEvent("shell", { command: 42 }, "/w"), null)
})

test("edit/write map path and content", () => {
  assert.deepEqual(toClaudeEvent("edit", { path: "a.py", oldString: "x", newString: "y" }, "/w"), {
    tool_name: "Edit",
    tool_input: { file_path: "a.py", new_content: "y" },
    cwd: "/w",
  })
  assert.deepEqual(toClaudeEvent("write", { path: "a.py", content: "y" }, "/w"), {
    tool_name: "Write",
    tool_input: { file_path: "a.py", new_content: "y" },
    cwd: "/w",
  })
  assert.equal(toClaudeEvent("patch", { patchText: "" }, "/w"), null)
})

test("patch expands only python add/update sections", () => {
  const patchText = [
    "*** Add File: src/new.py",
    "@@ new file",
    "*** Update File: README.md",
    "*** Update File: src/old.py",
    "*** Delete File: gone.py",
  ].join("\n")
  const events = patchEvents({ patchText }, "/w")
  assert.deepEqual(
    events.map((e) => e.tool_input.file_path),
    ["src/new.py", "src/old.py"],
  )
  assert.ok(events.every((e) => e.tool_name === "MultiEdit" && e.cwd === "/w"))
  assert.deepEqual(patchEvents({ patchText: "no sections" }, "/w"), [])
  assert.deepEqual(patchEvents({}, "/w"), [])
})

test("result text helpers", () => {
  assert.equal(resultText({ content: "hello" }), "hello")
  assert.equal(
    resultText({ content: [{ type: "text", text: "a" }, { type: "file", uri: "x" } as never, { type: "text", text: "b" }] }),
    "a\n\nb",
  )
  assert.equal(resultText({}), "")

  const replaced = withResultText({ content: "old", metadata: { m: 1 } }, "new")
  assert.equal((replaced as { content: string }).content, "new")
  assert.deepEqual((replaced as { metadata: unknown }).metadata, { m: 1 })

  const r: { content?: unknown } = { content: "base" }
  appendResultText(r, "feedback")
  assert.equal(r.content, "base\n\nfeedback")
  const empty: { content?: unknown } = {}
  appendResultText(empty, "feedback")
  assert.equal(empty.content, "feedback")
})

test("parseHookStdout", () => {
  assert.equal(parseHookStdout(""), null)
  assert.deepEqual(parseHookStdout('{"decision":"block","reason":"fix it"}'), { kind: "nudge", text: "fix it" })
  assert.equal(parseHookStdout('{"systemMessage":"needs python"}'), null)
  assert.deepEqual(parseHookStdout("plain text"), { kind: "nudge", text: "plain text" })
})
