# Mysterium IP Rotator for OpenCode

Automatically rotate residential IPs via [Mysterium Network](https://mysterium.network) to bypass free-tier rate limits on AI coding services like OpenCode, Claude Code, and Codex CLI.

**Why residential IPs?** Datacenter IPs (cloud, VPS) are easily detected and blocked by AI services. Residential IPs are real home connections — indistinguishable from a regular user.

---

## The Problem

AI coding tools (OpenCode free tier, etc.) rate-limit by IP address:

- 150 requests/day per IP → exhausted in minutes
- 429 errors break your workflow
- Switching WiFi isn't practical

## The Solution

Mysterium is a **decentralized VPN** with **20,000+ residential IPs** across **135+ countries**. Real people share their home bandwidth and earn MYST tokens. You connect through their residential IP — looks like a regular home user.

---

## Pricing

| Item | Cost |
|------|------|
| MYST token price | ~$0.12 USD |
| Data cost | ~3.29 MYST per GiB (~$0.40/GiB) |
| **Minimum to start** | **~1 MYST (~$0.12)** + ~0.1 POL (~$0.01) for gas |
| **Recommended to start** | **~5 MYST (~$0.60)** + ~0.5 POL (~$0.04) for gas |
| AI coding (50-100 MB/day) | ~0.15-0.33 MYST/day (~$0.02-0.04/day) |
| 5 MYST (~$0.60) lasts | ~15-30 days of daily AI coding |
| No subscription, no monthly fee | Pay only for what you use |

**You can start with as little as 1 MYST (~$0.12) + ~0.1 POL (~$0.01) for gas.** We recommend 5 MYST + 0.5 POL for a smooth start. That's it — no monthly fees, no subscriptions.

**No starter pack required.** Buy MYST on any exchange (Coinbase, Kraken, MEXC, etc.), send to your wallet address on **Polygon network**, and you're ready.

---

## Quick Start

### 1. Start the Mysterium node (Docker — easiest)

```bash
docker run -d \
  --cap-add NET_ADMIN \
  --net host \
  --name myst \
  --restart unless-stopped \
  -v myst-data:/var/lib/mysterium-node \
  mysteriumnetwork/myst:latest \
  daemon
```

This runs in **consumer mode** — it's a VPN client, not a provider. It does NOT share your bandwidth.

### 2. Create an identity (your wallet)

```bash
myst-rotator identity
```

This prints your identity address (e.g. `0x48ef2603610620ce4cd2764d9a208ed3cd56b0d8`).

### 3. Fund it (one-time)

Send **both** tokens to your identity address **on Polygon network**:

| Token | Amount | Why |
|-------|--------|-----|
| **MYST** | ~5 (~$0.60) | Pay for VPN data (~3.29 MYST/GiB) |
| **POL** | ~0.5 (~$0.04) | Gas for registration + transactions |

Where to get them:
- **MYST**: Coinbase, Kraken, MEXC, Uniswap (Polygon). Send on **Polygon** (chain 137), not Ethereum mainnet
- **POL**: Any exchange or Polygon faucet (~$0.05 is enough to start)

The identity auto-registers once it has POL for gas.

### 4. Install the rotator

```bash
git clone https://github.com/NosytLabs/myst-opencode-rotator.git
cd myst-opencode-rotator
./install.sh
```

### 5. Connect & rotate

```bash
# Check balance
myst-rotator balance

# Connect to a random residential IP
myst-rotator connect

# Check your new IP
myst-rotator ip

# Rotate to a different country
myst-rotator rotate

# Auto-rotate every 10 minutes
myst-rotator daemon --interval 600
```

---

## Usage

```bash
# Connect to a specific country
myst-rotator connect --country US

# Check status (connection, balance, identity)
myst-rotator status

# List available residential nodes
myst-rotator proposals --country US

# Rotate to new IP (different country)
myst-rotator rotate

# Run as daemon (auto-rotates)
myst-rotator daemon --interval 600

# Check daemon status
myst-rotator daemon-status

# Stop daemon
myst-rotator daemon-stop

# Check MYST balance
myst-rotator balance

# Show identity address
myst-rotator identity

# Disconnect
myst-rotator disconnect
```

---

## How It Works

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  OpenCode   │────▶│  Mysterium Node  │────▶│  Residential IP │
│  (or other) │     │  (WireGuard)     │     │  (real home)    │
└─────────────┘     └──────────────────┘     └─────────────────┘
                           │
                    ┌──────┴──────┐
                    │  On 429:    │
                    │  rotate()   │
                    │  → new IP   │
                    └─────────────┘
```

1. The `myst` node (Docker) runs in consumer mode and exposes a TequilAPI on `127.0.0.1:4050`
2. `myst-rotator connect` finds a residential node and creates a WireGuard tunnel through it
3. All traffic from your machine routes through that residential IP
4. When rate-limited (429), `myst-rotator rotate` switches to a new country/IP
5. OpenCode retries with the new IP → succeeds

---

## OpenCode Integration

### Option A: System-wide (simplest)

```bash
# Connect once, then just use OpenCode normally
myst-rotator connect --country US
opencode run -m "opencode/minimax-m3.1-flash-free" "hello"
```

### Option B: With the OpenCode plugin (auto-rotate on 429)

The `opencode-plugin/` directory contains an OpenCode plugin that automatically
rotates your IP when a 429 (rate limit) error is hit.

**Install:**

```bash
# Method 1: npm (after publishing)
opencode plugin myst-rotator

# Method 2: Local install
cd myst-opencode-rotator/opencode-plugin
npm install
npm link  # or: ln -s $(pwd) ~/.config/opencode/node_modules/myst-rotator
```

**Configure in `~/.config/opencode/opencode.json`:**

```json
{
  "plugin": ["myst-rotator"]
}
```

The plugin hooks into OpenCode's `chat.error` and `tool.error` events.
When a 429 is detected, it calls `myst-rotator rotate` and retries the request.

### Option C: Split tunnel (advanced)

Only route OpenCode traffic through the WireGuard interface using `ip rule` + `ip route`. Your other traffic stays on your normal connection.

---

## Mysterium Network

### What is Mysterium?

- **Decentralized VPN** — no central servers, no logs, no single point of failure
- **Residential IPs** — 20,000+ real home connections across 135+ countries
- **Pay-as-you-go** — pay only for what you use, no subscriptions
- **Open source** — [github.com/mysteriumnetwork](https://github.com/mysteriumnetwork)

### MYST Token

MYST is the native utility token powering the network:

- **For users:** Pay for VPN data with MYST
- **For node runners:** Earn MYST by sharing your bandwidth via [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97)
- **Exchanges:** Coinbase, Kraken, MEXC, and others
- **Price:** ~$0.12 USD

### Run a Node (Earn Free MYST)

Want to earn MYST while helping the network?

```bash
# Docker (provider mode — shares bandwidth, earns MYST)
docker run --cap-add NET_ADMIN -d -p 4449:4449 \
  --name myst-provider -v myst-provider-data:/var/lib/mysterium-node \
  --restart unless-stopped mysteriumnetwork/myst:latest \
  service --agreed-terms-and-conditions
```

Or use [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) for a GUI installer (Windows/Mac/Linux/Android). **[Sign up with this link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) to support this project.**

### Links

- [Mysterium Network](https://www.mysterium.network) — protocol & infrastructure
- [Mysterium Dark](https://www.mysteriumdark.com) — pay-as-you-go with crypto/card
- [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) — run a node, earn MYST ([referral link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97))
- [Docs](https://docs.mysterium.network) — technical documentation
- [Discord](https://discord.com/invite/n3vtSwc) — community
- [Stats](https://stats.mysterium.network) — live network stats

---

## Support This Project

- ⭐ Star this repo
- Run a [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) node ([referral link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97)) — earn MYST while helping the network
- Share this project with others who use AI coding tools

---

## Requirements

- Linux (Ubuntu/Debian/Fedora/Arch)
- Docker (or native `myst` binary)
- WireGuard kernel module
- MYST tokens (~1 minimum) + a little POL for Polygon gas

## Installation

### From source

```bash
git clone https://github.com/NosytLabs/myst-opencode-rotator.git
cd myst-opencode-rotator
./install.sh
```

### Manual

```bash
chmod +x myst_rotator.py
sudo ln -s $(pwd)/myst_rotator.py /usr/local/bin/myst-rotator
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Connection refused` | Start the node: `docker start myst` |
| `No identity` | Run: `myst-rotator identity` |
| `insufficient balance` | Send MYST + POL to your identity on Polygon |
| `registration InProgress` | Needs POL for gas. Send ~0.1 POL on Polygon |
| `no residential proposals` | Try a different country: `myst-rotator connect --country US` |
| `rate limited even with VPN` | Service may block all VPN IP ranges; try a different country |
| Docker not running | `sudo systemctl start docker` |

---

## Security

- This tool does **not** log your traffic — it only manages the VPN connection
- Mysterium uses WireGuard (industry-standard encryption)
- Your real IP is never exposed to the services you connect to
- The rotator only stores connection metadata in `~/.config/myst-rotator/`

---

## Contributing

PRs welcome! Areas for improvement:

- HTTP proxy server that auto-rotates on 429
- Split-tunnel / policy routing (only route OpenCode traffic)
- Docker Compose setup
- Publish plugin to npm as `myst-rotator`
- Support for multiple concurrent tunnels (IP pool)

## License

MIT — see [LICENSE](LICENSE)

---

**Built with [Mysterium Network](https://mysterium.network) — decentralized VPN powered by residential IPs and MYST tokens.**