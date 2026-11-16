#!/usr/bin/env bash
# Mysterium IP Rotator installer
set -euo pipefail

echo "=== Mysterium IP Rotator Installer ==="

# Check for mystvpn
if ! command -v mystvpn &>/dev/null; then
  echo "[1/3] Installing mystvpn CLI..."
  curl -fsSL https://github.com/mysteriumnetwork/mysteriumvpncli/releases/latest/download/install.sh | bash
else
  echo "[1/3] mystvpn already installed ($(mystvpn version 2>/dev/null || echo 'unknown'))"
fi

# Install rotator
echo "[2/3] Installing myst-rotator..."
mkdir -p ~/.local/bin
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/myst_rotator.py"
ln -sf "$SCRIPT_DIR/myst_rotator.py" ~/.local/bin/myst-rotator
echo "  Installed to ~/.local/bin/myst-rotator"

# Create config dir
mkdir -p ~/.config/myst-rotator

# Check auth status
echo "[3/3] Checking authentication..."
if mystvpn status 2>&1 | grep -qi "connected"; then
  echo "  Authenticated."
else
  echo "  Not authenticated. Run: sudo mystvpn auth"
  echo "  (Opens browser to sign in with Mysterium account)"
fi

echo ""
echo "=== Done! ==="
echo "Quick start:"
echo "  1. sudo mystvpn auth          # sign in (browser)"
echo "  2. myst-rotator connect       # connect to residential IP"
echo "  3. myst-rotator status        # check status"
echo "  4. myst-rotator rotate        # rotate to new IP"
echo "  5. myst-rotator daemon        # auto-rotate every 10 min"
echo ""
echo "Need MYST tokens? Buy ~1-10 MYST (~$0.12-1.20) on any exchange,"
echo "send to your Mysterium wallet address. That's it."