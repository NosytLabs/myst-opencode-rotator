/**
 * myst-rotator — OpenCode plugin
 *
 * Routes OpenCode model traffic through a Mysterium residential exit and rotates
 * that exit on a timer, so IP-scoped rate limits are avoided instead of hit.
 *
 * Verified against the live OpenCode plugin runtime (v2 API). At setup time the
 * available domains are:
 *
 *   options, agent, aisdk, catalog, command, integration, plugin, reference, skill
 *
 * There is NO `session` domain and therefore no `retry` hook in this build, so a
 * plugin cannot catch a 429 and re-issue the request itself. This plugin instead
 * rotates proactively on an interval: rotating before the limit is reached is
 * strictly better than reacting to it, and needs no platform support.
 *
 * Users only need: Docker + a funded Mysterium identity (MYST tokens).
 * No VPN client, no Mullvad, no split-tunnel configuration.
 *
 * Configuration (plugin options win over env, env over default):
 *
 *   env  MYST_ROTATOR_EVERY_MIN   minutes between rotations (default 10, 0 = off)
 *   env  MYST_ROTATOR_CONTROL     control socket URL (default http://127.0.0.1:8787)
 *
 *   opencode.json:
 *   {
 *     "plugin": [["myst-rotator", { "rotateEveryMin": 5 }]]
 *   }
 */

import { Plugin } from "@opencode/plugin"

/** Loopback control socket published by `myst-rotator serve`. */
const CONTROL_URL = process.env.MYST_ROTATOR_CONTROL || "http://127.0.0.1:8787"

/** Proxy env vars that point child processes at the residential exit. */
const PROXY_KEYS = [
  "HTTP_PROXY",
  "http_proxy",
  "HTTPS_PROXY",
  "https_proxy",
  "ALL_PROXY",
  "all_proxy",
]

/** Loopback must never go through the proxy. */
const NO_PROXY = "localhost,127.0.0.1,::1"

/** Default minutes between rotations. */
const DEFAULT_EVERY_MIN = 10

/** GET /status from the control socket. Returns null when there is no session. */
async function readStatus() {
  try {
    const res = await fetch(`${CONTROL_URL}/status`)
    if (!res.ok) return null
    const body = await res.json()
    if (!body.connected || !body.proxy) return null
    return { proxy: body.proxy, ip: body.ip || "?", country: body.country || "?" }
  } catch {
    return null
  }
}

/** POST /rotate: connect to a new residential exit, return its endpoint. */
async function rotate(reason) {
  const res = await fetch(`${CONTROL_URL}/rotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => "")
    throw new Error(`${res.status} ${text}`)
  }
  const body = await res.json()
  if (!body.proxy) throw new Error("rotate returned no proxy endpoint")
  return { proxy: body.proxy, ip: body.ip || "?", country: body.country || "?" }
}

/** Point this process at the residential exit. Returns a restore function. */
function applyProxy(proxy) {
  const previous = Object.fromEntries(PROXY_KEYS.map((key) => [key, process.env[key]]))
  for (const key of PROXY_KEYS) process.env[key] = proxy
  process.env.NO_PROXY = NO_PROXY
  process.env.no_proxy = NO_PROXY
  return () => {
    for (const key of PROXY_KEYS) {
      const value = previous[key]
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
}

/**
 * Rotation interval in ms. Plugin options win over env; 0 or a negative value
 * disables the timer. Falls back to the default when neither is set.
 */
function rotationIntervalMs(options) {
  const optionValue = Number(options?.rotateEveryMin)
  const envValue = Number(process.env.MYST_ROTATOR_EVERY_MIN)
  let minutes
  if (Number.isFinite(optionValue)) minutes = optionValue
  else if (process.env.MYST_ROTATOR_EVERY_MIN !== undefined && Number.isFinite(envValue)) {
    minutes = envValue
  } else minutes = DEFAULT_EVERY_MIN
  if (!Number.isFinite(minutes) || minutes < 0) return DEFAULT_EVERY_MIN * 60_000
  return Math.round(minutes * 60_000)
}

/** Human-readable interval: "3 sec" or "10 min". */
function describeInterval(ms) {
  if (ms < 60_000) return `${Math.round(ms / 1000)} sec`
  return `${Math.round(ms / 60_000)} min`
}

export default Plugin.define({
  id: "myst-rotator",

  async setup(ctx) {
    const options = ctx.options || {}
    let restore = () => {}

    // 1. Apply the residential proxy for this process so every provider call
    //    leaves through Mysterium. If no session is up, say so and continue.
    const status = await readStatus()
    if (status) {
      restore = applyProxy(status.proxy)
      console.log(
        `[myst-rotator] Routing through ${status.ip} (${status.country}) via ${status.proxy}`,
      )
    } else {
      console.log(
        "[myst-rotator] No active Mysterium session. Run: myst-rotator connect",
      )
    }

    // 2. Rotate on a timer. This is the point: a fresh residential IP before an
    //    IP-scoped limit is reached, so the 429 never happens. `unref()` keeps the
    //    timer from holding the process open.
    const everyMs = rotationIntervalMs(options)
    let timer
    let rotating = false
    const rotateNow = async (reason) => {
      // One rotation at a time; never overlap.
      if (rotating) return
      rotating = true
      try {
        const next = await rotate(reason)
        restore()
        restore = applyProxy(next.proxy)
        console.log(
          `[myst-rotator] ${reason}: now ${next.ip} (${next.country}) via ${next.proxy}`,
        )
      } catch (error) {
        console.log(`[myst-rotator] ${reason}: rotation failed: ${String(error)}`)
      } finally {
        rotating = false
      }
    }
    if (everyMs > 0) {
      timer = setInterval(() => void rotateNow("timer"), everyMs)
      if (typeof timer.unref === "function") timer.unref()
      console.log(`[myst-rotator] Auto-rotation every ${describeInterval(everyMs)}`)
    } else {
      console.log("[myst-rotator] Auto-rotation disabled (interval 0)")
    }

    // 3. Slash command: rotate now and report the new exit.
    try {
      await ctx.command.transform((draft) => {
        draft.add({
          name: "myst",
          description:
            "Rotate the Mysterium residential exit IP now (and show the new IP)",
          execute: async () => {
            await rotateNow("manual")
            const current = await readStatus()
            if (!current) return "myst-rotator: rotation failed (see log)"
            return `myst-rotator: now routing through ${current.ip} (${current.country})`
          },
        })
      })
    } catch (error) {
      console.log(`[myst-rotator] Could not register /myst command: ${String(error)}`)
    }

    // 4. Restore the original proxy env and stop the timer on unload.
    return () => {
      if (timer) clearInterval(timer)
      restore()
    }
  },
})