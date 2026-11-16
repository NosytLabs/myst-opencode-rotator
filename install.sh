#!/usr/bin/env bash
# Mysterium IP Rotator installer
set -euo pipefail

echo "=== Mysterium IP Rotator Installer ==="

# 1. Check Docker / start myst node
echo "[1/4] Checking Mysterium node..."
if ! command -v docker &>/dev/null; then
  echo "  ERROR: Docker not installed. Install Docker first: https://docs.docker.com/get-docker/"
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -q '^myst$'; then
  echo "  myst node already running."
elif docker ps -a --format '{{.Names}}' | grep -q '^myst$'; then
  echo "  Starting existing myst node..."
  docker start myst
else
  echo "  Creating myst node (consumer + proxy mode)..."
  docker run -d \
    --cap-add NET_ADMIN \
    --device /dev/net/tun:/dev/net/tun \
    -p 127.0.0.1:4050:4050 \
    --name myst \
    --restart unless-stopped \
    -v myst-data:/var/lib/mysterium-node \
    mysteriumnetwork/myst:latest \
    --proxymode daemon
  echo "  Node started. Waiting for TequilAPI..."
  sleep 5
fi

# 2. Install Foundry (cast) — needed for the registration workaround (node#6190)
echo "[2/4] Checking Foundry (cast)..."
if ! command -v cast &>/dev/null && [ ! -x "$HOME/.foundry/bin/cast" ]; then
  echo "  Installing Foundry (cast)..."
  curl -L https://foundry.paradigm.xyz -o /tmp/foundry-install.sh
  bash /tmp/foundry-install.sh >/dev/null 2>&1
  export PATH="$HOME/.foundry/bin:$PATH"
  "$HOME/.foundry/bin/foundryup" >/dev/null 2>&1 || true
fi
if [ -x "$HOME/.foundry/bin/cast" ] || command -v cast &>/dev/null; then
  echo "  cast ready."
else
  echo "  WARNING: cast not found. Registration workaround will be unavailable."
  echo "    Install: curl -L https://foundry.paradigm.xyz | bash && foundryup"
fi

# 3. Install rotator
echo "[3/4] Installing myst-rotator..."
mkdir -p ~/.local/bin
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/myst_rotator.py"
ln -sf "$SCRIPT_DIR/myst_rotator.py" ~/.local/bin/myst-rotator
echo "  Installed to ~/.local/bin/myst-rotator"

# Create config dir
mkdir -p ~/.config/myst-rotator

# 4. Check status
echo "[4/4] Checking node status..."
if curl -s http://127.0.0.1:4050/healthcheck 2>/dev/null | grep -q "uptime"; then
  echo "  TequilAPI is live."
  IDENTITY=$(curl -s http://127.0.0.1:4050/identities 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['identities'][0]['id'] if d.get('identities') else '')" 2>/dev/null || echo "")
  if [ -n "$IDENTITY" ]; then
    echo "  Identity: $IDENTITY"
  fi
else
  echo "  WARNING: TequilAPI not reachable. Check: docker logs myst"
fi

echo ""
echo "=== Done! ==="
echo "Next: run the guided setup (creates/uses identity, funds, registers on-chain):"
echo "  myst-rotator setup"
echo ""
echo "Then:"
echo "  myst-rotator connect                  # connect to a residential exit"
echo "  myst-rotator rotate                   # rotate to a new exit/IP"
echo "  myst-rotator serve                    # control socket for the OpenCode plugin"
echo ""
echo "OpenCode plugin (auto-routes model traffic + /myst command):"
echo "  See README.md -> 'OpenCode plugin'"