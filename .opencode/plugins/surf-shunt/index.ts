/**
 * OpenCode V2 plugin: surf-shunt
 *
 * Runs the existing large-read hook script (plugins/surf-shunt/hooks/scripts/
 * large_read_hook.py) as an OpenCode execute.before hook on read/shell, so a
 * full read of a large file (or `cat`/`less`/`bat` of one in a shell command)
 * is blocked and the model is pointed at the bulk-reader skill — identical
 * behavior to the Claude Code PreToolUse hook.
 */

import { Plugin } from "@opencode/plugin"
import { isReadTool, runHookScript, toClaudeEvent } from "../../lib/hooks.ts"

const LARGE_READ_HOOK = "plugins/surf-shunt/hooks/scripts/large_read_hook.py"

export default Plugin.define({
  id: "surf-shunt",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", async (event) => {
      if (!isReadTool(event.tool)) return
      let cwd: string = ctx.location.directory
      try {
        const session = await ctx.session.get({ sessionID: event.sessionID }) as { location?: { directory?: string } }
        cwd = session.location?.directory ?? cwd
      } catch {
        // fall back to the plugin location
      }
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
