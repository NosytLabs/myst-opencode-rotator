/**
 * myst-rotator — OpenCode plugin
 *
 * Routes OpenCode model traffic through a Mysterium residential exit and lets the
 * user rotate the exit IP on demand (or when a rate limit hits).
 *
 * Verified against the live OpenCode plugin runtime (v2 API). The domains that
 * actually exist at setup time are:
 *
 *   options, agent, aisdk, catalog, command, integration, plugin, reference, skill
 *
 * There is NO `session` domain and therefore no `retry` hook in this build, so a
 * plugin cannot transparently catch a 429 and retry by itself. Rotation is exposed
 * as a slash command instead, and the proxy env is applied at load so all model
 * traffic leaves through the residential exit from the start.
 *
 * Users only need: Docker + a funded Mysterium identity (MYST tokens).
 * No VPN client, no Mullvad, no split-tunnel configuration.
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
async function rotate() {
  const res = await fetch(`${CONTROL_URL}/rotate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: "myst-rotator command" }),
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

export default Plugin.define({
  id: "myst-rotator",

  async setup(ctx) {
    const baseline = { ...process.env }
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

    // 2. Slash command: rotate now, and see the new exit.
    try {
      await ctx.command.transform((draft) => {
        draft.add({
          name: "myst",
          description:
            "Rotate the Mysterium residential exit IP (and show the new IP)",
          execute: async () => {
            let text
            try {
              const next = await rotate()
              restore()
              restore = applyProxy(next.proxy)
              text = `myst-rotator: now routing through ${next.ip} (${next.country})`
              console.log(`[myst-rotator] ${text}`)
            } catch (error) {
              text = `myst-rotator: rotate failed: ${String(error)}`
              console.log(`[myst-rotator] ${text}`)
            }
            return text
          },
        })
      })
    } catch (error) {
      console.log(`[myst-rotator] Could not register /myst command: ${String(error)}`)
    }

    // 3. Restore the original proxy env when the plugin unloads.
    return () => restore()
  },
})