/**
 * Mysterium IP Rotator — OpenCode Plugin
 *
 * Automatically rotates residential IPs via Mysterium VPN when
 * the AI provider returns a 429 (rate limited) error.
 *
 * Requires:
 *   - Mysterium node running in consumer mode (Docker)
 *   - myst-rotator CLI installed (see main README)
 *   - MYST tokens + POL gas in the identity wallet
 *
 * Installation:
 *   opencode plugin myst-rotator
 *
 * Or manually:
 *   Add to ~/.config/opencode/opencode.json:
 *   { "plugin": ["myst-rotator"] }
 */

import { execSync } from "child_process"

const ROTATOR = "myst-rotator"
const MAX_ROTATIONS = 3
const ROTATION_COOLDOWN_MS = 30_000 // 30s between rotations

let lastRotation = 0
let rotationCount = 0

function rotateIP() {
  const now = Date.now()
  if (now - lastRotation < ROTATION_COOLDOWN_MS) {
    console.warn("[myst-rotator] Cooldown active, skipping rotation")
    return false
  }
  if (rotationCount >= MAX_ROTATIONS) {
    console.warn(`[myst-rotator] Max rotations (${MAX_ROTATIONS}) reached, giving up`)
    return false
  }

  try {
    console.log("[myst-rotator] Rate limited — rotating residential IP...")
    execSync(`${ROTATOR} rotate`, { timeout: 60_000, stdio: "inherit" })
    lastRotation = Date.now()
    rotationCount++
    console.log(`[myst-rotator] IP rotated (attempt ${rotationCount}/${MAX_ROTATIONS})`)
    return true
  } catch (err) {
    console.error("[myst-rotator] Rotation failed:", err.message)
    return false
  }
}

function resetRotations() {
  rotationCount = 0
}

function isRateLimitError(error) {
  if (!error) return false
  const msg = (error.message || error.toString || "").toLowerCase()
  const status = error.status || error.statusCode || error.response?.status
  return (
    status === 429 ||
    msg.includes("429") ||
    msg.includes("rate limit") ||
    msg.includes("rate_limit") ||
    msg.includes("too many requests") ||
    msg.includes("quota exceeded") ||
    msg.includes("resource_exhausted")
  )
}

/**
 * OpenCode plugin entry point.
 *
 * Hooks into the chat/completion lifecycle to catch 429 errors
 * and rotate the IP before retrying.
 */
export async function MystRotatorPlugin({ client, project, directory, worktree }) {
  console.log("[myst-rotator] Plugin loaded — auto-rotation on 429 enabled")

  return {
    // Hook: before chat completion
    "chat.params": async (input, output) => {
      // Reset rotation count on new request
      resetRotations()
    },

    // Hook: on chat error (catches 429s)
    "chat.error": async (input, output) => {
      const error = output?.error || input?.error
      if (isRateLimitError(error)) {
        console.warn("[myst-rotator] 429 detected, rotating IP...")
        const rotated = rotateIP()
        if (rotated) {
          // Signal that the request should be retried
          output.retry = true
          output.error = null
        }
      }
    },

    // Hook: tool execution error (catches 429s from tool calls)
    "tool.error": async (input, output) => {
      const error = output?.error
      if (isRateLimitError(error)) {
        console.warn("[myst-rotator] Tool 429 detected, rotating IP...")
        const rotated = rotateIP()
        if (rotated) {
          output.retry = true
          output.error = null
        }
      }
    },

    // Hook: on successful completion (reset rotation count)
    "chat.completed": async (input, output) => {
      resetRotations()
    },
  }
}

export default MystRotatorPlugin