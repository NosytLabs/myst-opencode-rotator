#!/usr/bin/env bash
# Mysterium IP Rotator installer
set -euo pipefail

echo "=== Mysterium IP Rotator Installer ==="

# 1. Check Docker / start myst node
echo "[1/3] Checking Mysterium node..."
if ! command -v docker &>/dev/null; then
  echo "  ERROR: Docker not installed. Install Docker first."
  exit 1
fi

if docker ps --format '{{.Names}}' | grep -q '^myst$'; then
  echo "  myst node already running."
elif docker ps -a --format '{{.Names}}' | grep -q '^myst$'; then
  echo "  Starting existing myst node..."
  docker start myst
else
  echo "  Creating myst node (consumer mode)..."
  docker run -d \
    --cap-add NET_ADMIN \
    --net host \
    --name myst \
    --restart unless-stopped \
    -v myst-data:/var/lib/mysterium-node \
    mysteriumnetwork/myst:latest \
    daemon
  echo "  Node started. Waiting for TequilAPI..."
  sleep 5
fi

# 2. Install rotator
echo "[2/3] Installing myst-rotator..."
mkdir -p ~/.local/bin
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/myst_rotator.py"
ln -sf "$SCRIPT_DIR/myst_rotator.py" ~/.local/bin/myst-rotator
echo "  Installed to ~/.local/bin/myst-rotator"

# Create config dir
mkdir -p ~/.config/myst-rotator

# 3. Check status
echo "[3/3] Checking node status..."
if curl -s http://127.0.0.1:4050/healthcheck | grep -q "uptime"; then
  echo "  TequilAPI is live."
  IDENTITY=$(curl -s http://127.0.0.1:4050/identities | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['identities'][0]['id'] if d.get('identities') else '')" 2>/dev/null || echo "")
  if [ -n "$IDENTITY" ]; then
    echo "  Identity: $IDENTITY"
    echo ""
    echo "=== Fund your wallet ==="
    echo "Send MYST + POL (on Polygon network) to:"
    echo "  $IDENTITY"
    echo ""
    echo "~1-5 MYST (~$0.12-0.60) + ~0.1 POL (~$0.03) to start."
  else
    echo "  No identity yet. Run: myst-rotator identity"
  fi
else
  echo "  WARNING: TequilAPI not reachable. Check: docker logs myst"
fi

echo ""
echo "=== Done! ==="
echo "Quick start:"
echo "  1. Fund wallet (send MYST + POL on Polygon to identity above)"
echo "  2. myst-rotator balance        # check balance"
echo "  3. myst-rotator connect        # connect to residential IP"
echo "  4. myst-rotator status         # check status"
echo "  5. myst-rotator rotate         # rotate to new IP"
echo "  6. myst-rotator daemon         # auto-rotate every 10 min"