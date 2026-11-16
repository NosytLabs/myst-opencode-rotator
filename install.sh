#!/bin/bash
# Install Mysterium IP Rotator for OpenCode
set -euo pipefail

echo "=== Mysterium IP Rotator Installer ==="

# 1. Install mystvpn CLI if not present
if ! command -v mystvpn &>/dev/null; then
    echo "[1/4] Installing mystvpn CLI..."
    curl -fsSL https://github.com/mysteriumnetwork/mysteriumvpncli/releases/latest/download/install.sh | bash
else
    echo "[1/4] mystvpn already installed: $(mystvpn version 2>/dev/null || echo 'unknown')"
fi

# 2. Install rotator
echo "[2/4] Installing myst-rotator..."
chmod +x myst_rotator.py

if [ -d "$HOME/.local/bin" ]; then
    ln -sf "$(pwd)/myst_rotator.py" "$HOME/.local/bin/myst-rotator"
    echo "  Installed to ~/.local/bin/myst-rotator"
else
    mkdir -p "$HOME/.local/bin"
    ln -sf "$(pwd)/myst_rotator.py" "$HOME/.local/bin/myst-rotator"
    echo "  Installed to ~/.local/bin/myst-rotator"
fi

# 3. Create config dir
mkdir -p "$HOME/.config/myst-rotator"

# 4. Check auth
echo "[3/4] Checking mystvpn authentication..."
if mystvpn status &>/dev/null; then
    echo "  ✓ Authenticated"
else
    echo "  ⚠ Not authenticated. Run: sudo mystvpn auth"
fi

echo "[4/4] Done!"
echo ""
echo "Quick start:"
echo "  myst-rotator connect          # Connect to residential IP"
echo "  myst-rotator ip               # Check your new IP"
echo "  myst-rotator rotate           # Rotate to new country"
echo "  myst-rotator daemon --interval 600  # Auto-rotate every 10 min"
echo ""
echo "Don't forget to get MYST tokens:"
echo "  https://www.mysteriumdark.com  ($3.99 starter = years of coding)"