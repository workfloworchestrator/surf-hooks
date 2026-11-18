/**
 * OpenCode V2 plugin: surf-hooks
 *
 * One plugin that runs the existing Claude Code hook scripts
 * (the .py files under plugins/…/hooks/scripts/) as OpenCode tool/session hooks, so both
 * harnesses enforce exactly the same rules with zero duplicated logic:
 *
 *   - execute.before on edit/write/patch  → base_exception_hook.py (hard block
 *     by throwing, the V2 equivalent of exit code 2)
 *   - execute.after  on edit/write/patch  → python_style_hook.py and
 *     test_param_hook.py (nudge feedback appended to the tool result; a depth
 *     >= 3 nesting hard-block rewrites the result to the BLOCKED message)
 *   - session "prompt" hook               → python_style_primer.py (appends the
 *     style primer to Python-related user prompts)
 *   - execute.before on read/shell        → large_read_hook.py (blocks full
 *     reads of files over the line threshold and points at the bulk-reader
 *     skill; exit code 2 → thrown error)
 *
 * Load it from git in any project's opencode.json:
 *   "plugins": ["github:workfloworchestrator/surf-hooks#main"]
 */

import { Plugin } from "@opencode/plugin"
import {
  appendResultText,
  isEditTool,
  isReadTool,
  parseHookStdout,
  patchEvents,
  runHookScript,
  toClaudeEvent,
  withResultText,
  type HookScriptResult,
} from "../lib/hooks.ts"

const STYLE_SCRIPTS = "plugins/surf-python-style/hooks/scripts"
const STYLE_HOOK = `${STYLE_SCRIPTS}/python_style_hook.py`
const PARAM_HOOK = `${STYLE_SCRIPTS}/test_param_hook.py`
const BASE_EXCEPTION_HOOK = `${STYLE_SCRIPTS}/base_exception_hook.py`
const PRIMER_HOOK = `${STYLE_SCRIPTS}/python_style_primer.py`
const LARGE_READ_HOOK = "plugins/surf-shunt/hooks/scripts/large_read_hook.py"

/** Working directory for hook scripts: the session's own directory when known. */
async function sessionCwd(
  ctx: { location: { directory: string }; session: { get(input: { sessionID: string }): Promise<unknown> } },
  sessionID: string,
): Promise<string> {
  // cwd is only passed to the Python scripts as a plain string
  try {
    const session = (await ctx.session.get({ sessionID })) as { location?: { directory?: string } }
    return session.location?.directory ?? ctx.location.directory
  } catch {
    return ctx.location.directory
  }
}

/** Run one hook script for one Claude event; never throws. */
function check(
  script: string,
  event: { tool_name: string; tool_input: Record<string, unknown>; cwd: string },
): Promise<HookScriptResult> {
  return runHookScript(script, event, event.cwd)
}

export default Plugin.define({
  id: "surf-hooks",
  async setup(ctx) {
    // ── surf-python-style ──────────────────────────────────────────────────

    // Hard block: BaseException in new Python code fails the tool call outright
    // (V2 execute.before can throw; Claude Code used exit code 2 in PostToolUse).
    await ctx.tool.hook("execute.before", async (event) => {
      if (!isEditTool(event.tool)) return
      const cwd = await sessionCwd(ctx, event.sessionID)
      const events = event.tool === "patch" ? patchEvents(event.input, cwd) : [toClaudeEvent(event.tool, event.input, cwd)]
      for (const claudeEvent of events) {
        if (!claudeEvent) continue
        const result = await check(BASE_EXCEPTION_HOOK, claudeEvent)
        if (result.code === 2) throw new Error(result.stderr.trim() || "BLOCKED by surf-python-style")
      }
    })

    // Soft nudges after the write landed (PostToolUse equivalent).
    await ctx.tool.hook("execute.after", async (event) => {
      if (!isEditTool(event.tool) || event.status !== "completed") return
      const cwd = await sessionCwd(ctx, event.sessionID)
      const events = event.tool === "patch" ? patchEvents(event.input, cwd) : [toClaudeEvent(event.tool, event.input, cwd)]
      for (const claudeEvent of events) {
        if (!claudeEvent) continue
        for (const script of [STYLE_HOOK, PARAM_HOOK]) {
          const result = await check(script, claudeEvent)
          if (result.code === 2) {
            // Hard block (nesting depth >= 3): the write already happened, so
            // surface the block as the tool result instead of throwing.
            event.result = withResultText(event.result, result.stderr.trim())
            return
          }
          const feedback = parseHookStdout(result.stdout)
          if (feedback) appendResultText(event.result, feedback.text)
        }
      }
    })

    // UserPromptSubmit equivalent: prime Python-related prompts.
    await ctx.session.hook("prompt", async (event) => {
      const result = await runHookScript(PRIMER_HOOK, { prompt: event.prompt.text }, ctx.location.directory)
      const stdout = result.stdout.trim()
      if (!stdout) return
      try {
        const parsed = JSON.parse(stdout)
        const context = parsed?.hookSpecificOutput?.additionalContext
        if (typeof context === "string") event.prompt.text = `${event.prompt.text}\n\n${context}`
      } catch {
        // not JSON: nothing to inject
      }
    })

    // ── surf-shunt ─────────────────────────────────────────────────────────

    await ctx.tool.hook("execute.before", async (event) => {
      if (!isReadTool(event.tool) || isEditTool(event.tool)) return
      const cwd = await sessionCwd(ctx, event.sessionID)
      const claudeEvent = toClaudeEvent(event.tool, event.input, cwd)
      if (!claudeEvent) return
      const result = await runHookScript(LARGE_READ_HOOK, claudeEvent, cwd)
      if (result.code === 2) {
        // PreToolUse exit code 2 = block the tool call; in V2 that is a thrown
        // error, whose message is shown to the model.
        throw new Error(result.stderr.trim() || "BLOCKED by surf-shunt")
      }
      // run-python --fail-open emits {"systemMessage": ...} on stdout when no
      // suitable Python exists; the hook then fails open (call goes through),
      // so just surface the warning in the server log.
      const stdout = result.stdout.trim()
      if (stdout) {
        try {
          const parsed = JSON.parse(stdout)
          if (typeof parsed?.systemMessage === "string") console.warn(`[surf-shunt] ${parsed.systemMessage}`)
        } catch {
          // not JSON: ignore
        }
      }
    })
  },
})
