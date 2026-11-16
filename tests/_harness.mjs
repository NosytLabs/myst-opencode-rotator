// Minimal host for loading the myst-rotator plugin outside OpenCode.
// Lets the plugin's timer run and reports what it did as JSON on stdout.
import { pathToFileURL } from "node:url"

const control = process.env.TEST_CONTROL
const intervalMin = Number(process.env.TEST_INTERVAL_MIN)

// The plugin reads the control URL from env at import time.
process.env.MYST_ROTATOR_CONTROL = control

const logs = []
const origLog = console.log
console.log = (...args) => {
  const line = args.join(" ")
  logs.push(line)
  origLog("[plugin]", line)
}

const mod = await import(pathToFileURL(process.env.TEST_PLUGIN).href)
const plugin = mod.default

// Fake OpenCode context: only what the plugin actually uses.
const commands = []
const ctx = {
  options: { rotateEveryMin: intervalMin },
  command: {
    transform: async (fn) => {
      const draft = { add: (cmd) => commands.push(cmd) }
      fn(draft)
      return { dispose() {} }
    },
  },
  session: {
    synthetic: async () => {},
  },
}

const cleanup = await plugin.setup(ctx)

// Let the timer fire.
await new Promise((r) => setTimeout(r, Number(process.env.TEST_WAIT_MS)))

const proxyAfter = process.env.HTTPS_PROXY || process.env.https_proxy || ""

if (typeof cleanup === "function") await cleanup()

process.stdout.write(
  "\n__RESULT__" +
    JSON.stringify({ logs, commands: commands.map((c) => c.name), proxyAfter }) +
    "__RESULT__\n",
)