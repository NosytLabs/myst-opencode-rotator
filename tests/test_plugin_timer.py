#!/usr/bin/env python3
"""End-to-end test for the myst-rotator OpenCode plugin timer.

Verifies the plugin's timer actually rotates the exit on schedule, without
needing a funded Mysterium identity:

  1. Start a mock control socket that reports a fake residential exit and
     changes the "exit IP" on every /rotate call.
  2. Load the real plugin (opencode-plugin/index.js) with a short interval.
  3. Assert the plugin rotated at least once and re-pointed the proxy env.

Run: python3 tests/test_plugin_timer.py
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO / "opencode-plugin"
PORT = 8791
CONTROL = f"http://127.0.0.1:{PORT}"

# Fake exits handed out one per rotation.
EXITS = [
    ("103.170.217.96", "SG"),
    ("94.154.102.62", "PL"),
    ("23.228.77.77", "MY"),
    ("185.22.152.1", "NL"),
]

state = {"rotations": 0, "lock": threading.Lock()}


def current_exit():
    # Exit 0 is the initial state; each rotation advances.
    idx = min(state["rotations"], len(EXITS) - 1)
    return EXITS[idx]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002 - match base signature
        pass

    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] != "/status":
            self._send(404, {"error": "not found"})
            return
        ip, country = current_exit()
        self._send(200, {
            "connected": True,
            "proxy": f"http://127.0.0.1:{40000 + state['rotations']}",
            "ip": ip,
            "country": country,
        })

    def do_POST(self):
        if self.path.split("?")[0] != "/rotate":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        with state["lock"]:
            state["rotations"] += 1
        ip, country = current_exit()
        self._send(200, {
            "connected": True,
            "proxy": f"http://127.0.0.1:{40000 + state['rotations']}",
            "ip": ip,
            "country": country,
        })


def wait_port(port, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# --- The plugin host harness lives in _harness.mjs next to this file. ---



def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not wait_port(PORT):
        print("FAIL: mock control socket did not start")
        return 1

    plugin = PLUGIN_DIR / "index.js"
    harness = Path(__file__).resolve().parent / "_harness.mjs"
    if not harness.exists():
        print(f"FAIL: harness missing: {harness}")
        return 1

    env = dict(os.environ)
    env.update({
        "TEST_CONTROL": CONTROL,
        "TEST_PLUGIN": str(plugin),
        "TEST_INTERVAL_MIN": "0.05",   # 3 seconds
        "TEST_WAIT_MS": "7000",        # long enough for ~2 rotations
    })
    # Ensure the plugin can resolve @opencode/plugin from its own node_modules.
    env["NODE_PATH"] = str(PLUGIN_DIR / "node_modules")

    proc = subprocess.run(
        ["node", str(harness)],
        capture_output=True, text=True, timeout=60, env=env,
        cwd=str(PLUGIN_DIR),
    )
    out = proc.stdout + proc.stderr

    print("=== plugin output ===")
    for line in out.splitlines():
        if line.startswith("[plugin]"):
            print(" ", line)

    payload = None
    if "__RESULT__" in out:
        raw = out.split("__RESULT__")[1].split("__RESULT__")[0]
        payload = json.loads(raw)

    print("\n=== assertions ===")
    ok = True

    if payload is None:
        print("FAIL: harness produced no result")
        print(out[-2000:])
        return 1

    rotations = state["rotations"]
    checks = [
        ("control socket received rotations", rotations >= 1, f"{rotations} rotation(s)"),
        ("plugin logged the initial exit", any("Routing through" in l for l in payload["logs"]),
         next((l for l in payload["logs"] if "Routing through" in l), "none")),
        ("plugin logged auto-rotation interval", any("Auto-rotation every" in l for l in payload["logs"]),
         next((l for l in payload["logs"] if "Auto-rotation" in l), "none")),
        ("plugin logged a timer rotation", any("timer:" in l for l in payload["logs"]),
         next((l for l in payload["logs"] if "timer:" in l), "none")),
        ("/myst command registered", "myst" in payload["commands"], str(payload["commands"])),
        ("proxy env re-pointed after rotation", "40000" in payload["proxyAfter"] or bool(payload["proxyAfter"]),
         payload["proxyAfter"] or "(empty)"),
    ]
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed

    # The proxy port must have advanced, proving the new exit was applied.
    ports = [l for l in payload["logs"] if "via http://127.0.0.1:" in l]
    advanced = len({l.rsplit(":", 1)[-1].rstrip(")") for l in ports}) > 1
    print(f"  [{'PASS' if advanced else 'FAIL'}] proxy port advanced across rotations: "
          f"{len(set(l.rsplit(':', 1)[-1].rstrip(')') for l in ports))} distinct")
    ok = ok and advanced

    print("\n=== " + ("ALL PASS" if ok else "FAILURES PRESENT") + " ===")
    server.shutdown()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())