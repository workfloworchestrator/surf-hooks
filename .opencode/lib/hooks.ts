/**
 * Shared helpers for the OpenCode plugins in this repository.
 *
 * The heavy lifting (AST analysis, shell parsing) lives in the existing Python
 * hook scripts under plugins/ — these helpers only translate OpenCode V2 tool
 * hook events into the Claude Code hook JSON those scripts already speak, so
 * both harnesses run the exact same logic.
 *
 * Everything in here is pure (no plugin imports) so it can be unit-tested with
 * `node --experimental-strip-types --test .opencode/lib/hooks.test.ts`.
 */

import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import path from "node:path"

/** Absolute path of this repository (the directory containing .opencode/). */
export const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..")

export interface HookScriptResult {
  /** Process exit code. */
  code: number
  stdout: string
  stderr: string
}

/**
 * Run one of the existing Python hook scripts with a Claude-shaped event on
 * stdin, through plugins/surf-shunt/scripts/run-python so the first Python
 * >= 3.10 on PATH is used. Never throws: a missing interpreter or a crash is
 * reported as `{ code: -1, ... }` and the caller fails open.
 */
export function runHookScript(scriptRelPath: string, event: unknown, cwd: string): Promise<HookScriptResult> {
  const runPython = path.join(REPO_ROOT, "plugins/surf-shunt/scripts/run-python")
  const script = path.join(REPO_ROOT, scriptRelPath)
  const pluginData = process.env.CLAUDE_PLUGIN_DATA ?? path.join(process.env.HOME ?? "/tmp", ".claude")
  return new Promise((resolve) => {
    let child
    try {
      child = spawn(runPython, ["--fail-open", script], {
        cwd,
        env: { ...process.env, CLAUDE_PLUGIN_DATA: pluginData },
        stdio: ["pipe", "pipe", "pipe"],
      })
    } catch (error) {
      resolve({ code: -1, stdout: "", stderr: String(error) })
      return
    }
    let stdout = ""
    let stderr = ""
    child.stdout.on("data", (chunk: Buffer) => (stdout += chunk))
    child.stderr.on("data", (chunk: Buffer) => (stderr += chunk))
    child.on("error", (error) => resolve({ code: -1, stdout, stderr: stderr + String(error) }))
    child.on("close", (code) => resolve({ code: code ?? -1, stdout, stderr }))
    child.stdin.on("error", () => {})
    child.stdin.end(JSON.stringify(event))
  })
}

/** The Claude Code hook event shape the Python scripts expect. */
export interface ClaudeHookEvent {
  tool_name: string
  tool_input: Record<string, unknown>
  cwd: string
}

const EDIT_TOOLS = new Set(["edit", "write", "patch"])

/** True when the OpenCode tool writes Python files worth style-checking. */
export function isEditTool(tool: string): boolean {
  return EDIT_TOOLS.has(tool)
}

/** True when the OpenCode tool can pull a large file into context. */
export function isReadTool(tool: string): boolean {
  return tool === "read" || tool === "shell"
}

/**
 * Translate an OpenCode V2 `execute.*` event into the Claude Code hook event
 * the shared Python scripts understand. Returns null when the tool has no
 * meaningful file target.
 */
export function toClaudeEvent(tool: string, input: unknown, cwd: string): ClaudeHookEvent | null {
  const args = (input ?? {}) as Record<string, unknown>
  if (tool === "read") {
    if (typeof args.path !== "string") return null
    const tool_input: Record<string, unknown> = { file_path: args.path }
    if (args.offset !== undefined) tool_input.offset = args.offset
    if (args.limit !== undefined) tool_input.limit = args.limit
    return { tool_name: "Read", tool_input, cwd }
  }
  if (tool === "shell") {
    if (typeof args.command !== "string") return null
    return { tool_name: "Bash", tool_input: { command: args.command }, cwd }
  }
  if (tool === "edit" || tool === "write") {
    const filePath = args.path ?? args.filePath
    if (typeof filePath !== "string") return null
    // The PostToolUse scripts prefer new_content from the event; the scripts
    // fall back to reading the file from disk when it is absent, which is the
    // correct content in an execute.after hook.
    const tool_input: Record<string, unknown> = { file_path: filePath }
    const content = args.content ?? args.newString
    if (typeof content === "string") tool_input.new_content = content
    return { tool_name: tool === "edit" ? "Edit" : "Write", tool_input, cwd }
  }
  if (tool === "patch") {
    // patch carries a whole patchText; run the checks per affected .py file.
    // Handled by patchEvents() — a single patch is not one Claude event.
    return null
  }
  return null
}

/**
 * Expand an OpenCode `patch` tool input into one Claude event per Python file
 * the patch touches. Only `*** Add File:` / `*** Update File:` sections are
 * considered; the style scripts re-read the written file from disk anyway.
 */
export function patchEvents(input: unknown, cwd: string): ClaudeHookEvent[] {
  const args = (input ?? {}) as Record<string, unknown>
  if (typeof args.patchText !== "string") return []
  const events: ClaudeHookEvent[] = []
  for (const match of args.patchText.matchAll(/^\*\*\* (?:Add|Update) File: (.+)$/gm)) {
    const file = match[1].trim()
    if (file.endsWith(".py")) events.push({ tool_name: "MultiEdit", tool_input: { file_path: file }, cwd })
  }
  return events
}

/** Text content of a V2 Tool.Result, as a single string (content may be a string or Content[]). */
export function resultText(result: { content?: string | ReadonlyArray<{ type: string; text?: string }> }): string {
  if (typeof result.content === "string") return result.content
  if (Array.isArray(result.content)) return result.content.map((part) => part.text ?? "").join("\n")
  return ""
}

/** Replace the text content of a V2 Tool.Result, keeping file parts and metadata intact. */
export function withResultText<T extends { content?: unknown }>(result: T, text: string): T {
  if (typeof result.content === "string" || result.content === undefined) {
    return { ...result, content: text }
  }
  const parts = (result.content as ReadonlyArray<unknown>).map((part) =>
    part && typeof part === "object" && (part as { type?: string }).type === "text"
      ? { ...(part as object), text }
      : part,
  )
  return { ...result, content: parts.length === 1 && typeof (parts[0] as { type?: string }).type === "string" ? parts : parts }
}

/** Append a feedback block to a V2 Tool.Result's text content. */
export function appendResultText(result: { content?: unknown }, extra: string): void {
  const current = resultText(result as { content?: string | ReadonlyArray<{ type: string; text?: string }> })
  ;(result as { content?: unknown }).content = current ? `${current}\n\n${extra}` : extra
}

/**
 * Interpret a PostToolUse hook script's stdout: `{"decision": "block",
 * "reason": "..."}` is a nudge. Returns null when the script produced no
 * feedback. (The `{"systemMessage": ...}` line from `run-python --fail-open`
 * is handled separately by the caller.)
 */
export function parseHookStdout(stdout: string): { kind: "nudge"; text: string } | null {
  const trimmed = stdout.trim()
  if (!trimmed) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (typeof parsed?.reason === "string") return { kind: "nudge", text: parsed.reason }
    return null
  } catch {
    // Not JSON: treat the whole stdout as a plain message.
    return { kind: "nudge", text: trimmed }
  }
}
