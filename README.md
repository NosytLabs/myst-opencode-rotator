# Mysterium IP Rotator for OpenCode

Automatically rotate residential IPs via [Mysterium VPN](https://www.mysteriumvpn.com) to bypass free-tier rate limits on AI coding services like OpenCode, Claude Code, and Codex CLI.

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
| Data cost | ~0.1-0.3 MYST per GB (~$0.01-0.04/GB) |
| **Minimum to start** | **~1 MYST (~$0.12)** — yes, that's it |
| AI coding (50-100 MB/day) | **months/years** on 10 MYST (~$1.20) |
| No subscription, no monthly fee | Pay only for what you use |

**You can start with as little as 1 MYST (~$0.12).** It won't last long (maybe a few days of light coding), but it's enough to test. For serious use, 10-20 MYST (~$1.20-2.40) lasts years.

**No starter pack required.** Buy MYST on any exchange (Coinbase, Kraken, MEXC, etc.), send to your Mysterium wallet address, and you're ready.

---

## Quick Start

### 1. Get MYST tokens (one-time)

1. Install the Mysterium app or `mystvpn` CLI (below)
2. Buy **~10-20 MYST** on any exchange (~$1.20-2.40)
3. Send MYST to your Mysterium wallet address (shown in the app/CLI)
4. Done — pay-as-you-go, no subscription

> **Want to earn free MYST?** Run a [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) node and share unused bandwidth to earn MYST. No technical skills needed — runs on Raspberry Pi, Docker, or desktop. Sign up with [this link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) to support this project.

### 2. Install mystvpn CLI

```bash
curl -fsSL https://github.com/mysteriumnetwork/mysteriumvpncli/releases/latest/download/install.sh | bash
```

### 3. Authenticate

```bash
sudo mystvpn auth
```

Opens browser → sign in → approve. Your MYST wallet is linked.

### 4. Install the rotator

```bash
git clone https://github.com/NosytLabs/myst-opencode-rotator.git
cd myst-opencode-rotator
chmod +x myst_rotator.py
sudo ln -s $(pwd)/myst_rotator.py /usr/local/bin/myst-rotator
# or: ./install.sh
```

### 5. Connect & rotate

```bash
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

# Check status
myst-rotator status

# List available countries
myst-rotator countries

# Rotate to new IP (different country)
myst-rotator rotate

# Run as daemon (auto-rotates)
myst-rotator daemon --interval 600

# Check daemon status
myst-rotator daemon-status

# Stop daemon
myst-rotator daemon-stop

# Disconnect
myst-rotator disconnect
```

---

## How It Works

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  OpenCode   │────▶│  mystvpn CLI │────▶│  Residential IP │
│  (or other) │     │  (WireGuard) │     │  (real home)    │
└─────────────┘     └──────────────┘     └─────────────────┘
                           │
                    ┌──────┴──────┐
                    │  On 429:    │
                    │  rotate()   │
                    │  → new IP   │
                    └─────────────┘
```

1. `mystvpn connect` creates a WireGuard tunnel to a residential node
2. All traffic from your machine routes through that residential IP
3. When rate-limited (429), `myst-rotator rotate` switches to a new country/IP
4. OpenCode retries with the new IP → succeeds

---

## OpenCode Integration

### Option A: System-wide (simplest)

```bash
# Connect once, then just use OpenCode normally
myst-rotator connect --country US
opencode run -m "opencode/minimax-m3.1-flash-free" "hello"
```

### Option B: With an OpenCode plugin (planned)

A plugin that intercepts 429 responses and calls `myst-rotator rotate` automatically. See `plugins/` directory for the WIP plugin.

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
- **For node runners:** Earn MYST by sharing your bandwidth via [MystNodes](https://www.mystnodes.com)
- **Exchanges:** Coinbase, Kraken, MEXC, and others
- **Price:** ~$0.12 USD

### Run a Node (Earn MYST)

Want to earn MYST while helping the network?

```bash
# Docker (easiest)
docker run --cap-add NET_ADMIN -d -p 4449:4449 \
  --name myst -v myst-data:/var/lib/mysterium-node \
  --restart unless-stopped mysteriumnetwork/myst:latest \
  service --agreed-terms-and-conditions
```

Or use [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) for a GUI installer (Windows/Mac/Linux/Android). **[Sign up with this link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) to support this project.**

### Links

- [Mysterium VPN](https://www.mysteriumvpn.com) — consumer VPN
- [Mysterium Dark](https://www.mysteriumdark.com) — pay-as-you-go with crypto/card
- [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) — run a node, earn MYST ([referral link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97))
- [Mysterium Network](https://www.mysterium.network) — protocol & infrastructure
- [Docs](https://docs.mysterium.network) — technical documentation
- [Discord](https://discord.com/invite/n3vtSwc) — community
- [Stats](https://stats.mysterium.network) — live network stats

---

## Support This Project

- ⭐ Star this repo
- Run a [MystNodes](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97) node ([referral link](https://mystnodes.co/?referral_code=NhzVTqGyKZcjPDLRdBE2Vw8lJRkkZSnzkbvrrJ97)) — earn MYST while helping the network
- Sign up for [Mysterium VPN](https://www.mysteriumvpn.com) (consumer VPN, separate from CLI)
- Share this project with others who use AI coding tools

---

## Requirements

- Linux (Ubuntu/Debian/Fedora/Arch)
- WireGuard kernel module
- `mystvpn` CLI installed and authenticated
- MYST tokens (~10 minimum)

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
| `mystvpn: command not found` | Install: `curl -fsSL https://github.com/mysteriumnetwork/mysteriumvpncli/releases/latest/download/install.sh \| bash` |
| `auth expired` | Re-run `sudo mystvpn auth` |
| `no residential nodes in <country>` | Try a different country: `myst-rotator connect --country US` |
| `WireGuard handshake failed` | Check `sudo wg show` — may need to restart `mystvpn` |
| `rate limited even with VPN` | Service may block all VPN IP ranges; try a different country |
| `insufficient balance` | Top up MYST tokens in your Mysterium wallet |

---

## Security

- This tool does **not** log your traffic — it only manages the VPN connection
- Mysterium VPN uses WireGuard (industry-standard encryption)
- Your real IP is never exposed to the services you connect to
- The rotator only stores connection metadata in `~/.config/myst-rotator/`

---

## Contributing

PRs welcome! Areas for improvement:

- HTTP proxy server that auto-rotates on 429
- Split-tunnel / policy routing (only route OpenCode traffic)
- Docker Compose setup
- Integration with OpenCode's plugin system
- Support for multiple concurrent tunnels (IP pool)

## License

MIT — see [LICENSE](LICENSE)

---

**Built with [Mysterium VPN](https://www.mysteriumvpn.com) — decentralized VPN powered by residential IPs and MYST tokens.**