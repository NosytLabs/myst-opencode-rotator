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

```bash
# 1. Install the node + rotator (Docker)
curl -fsSL https://raw.githubusercontent.com/NosytLabs/myst-opencode-rotator/main/install.sh | bash

# 2. Start the node + rotator, then guided setup
myst-rotator up
myst-rotator setup      # creates identity, tells you where to send MYST + POL

# 3. Connect and install the OpenCode plugin
myst-rotator connect
myst-rotator serve &    # control socket for the plugin
```

That's it. **No VPN client required** — you never touch Mullvad, WireGuard, or
split-tunnel settings. You just need **MYST tokens** (plus a little POL for gas).

Your traffic leaves through a residential IP; your own connection is untouched.

### 1. Start the Mysterium node (Docker)

```bash
docker run -d \
  --cap-add NET_ADMIN \
  --device /dev/net/tun:/dev/net/tun \
  -p 127.0.0.1:4050:4050 \
  --name myst \
  --restart unless-stopped \
  -v myst-data:/var/lib/mysterium-node \
  mysteriumnetwork/myst:latest \
  --proxymode daemon
```

The `--proxymode` flag makes the node expose a **local HTTP proxy** (on a
loopback port) that carries only the traffic you point at it. The node runs in
its own network namespace, so it never rewrites your host's routing table.

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

The identity auto-registers once it has POL for gas. **If it gets stuck
`registration InProgress`** (a known, open Mysterium bug — [node#6190](https://github.com/mysteriumnetwork/node/issues/6190)),
run the workaround:

```bash
myst-rotator register   # pre-funds the channel + registers directly on-chain with cast
```

See [The registration bug](#the-registration-bug) below for the full explanation.

### 4. Install the rotator

```bash
git clone https://github.com/NosytLabs/myst-opencode-rotator.git
cd myst-opencode-rotator
./install.sh
```

Then see **Usage** below for the full command list.

---

## Usage

```bash
# Start the node (proxy mode, own network namespace)
myst-rotator up

# Guided setup: identity, funding address, on-chain registration
myst-rotator setup

# Connect to a residential exit
myst-rotator connect
myst-rotator connect --country US

# Check status (exit IP, country, balance, identity)
myst-rotator status

# List available residential nodes
myst-rotator proposals --country US

# Rotate to a new IP/country now
myst-rotator rotate

# Control socket for the OpenCode plugin
myst-rotator serve

# Check MYST balance / show identity / disconnect
myst-rotator balance
myst-rotator identity
myst-rotator disconnect
```

---

## How It Works

```
┌──────────────┐   HTTP_PROXY   ┌───────────────────┐   WireGuard   ┌───────────────┐
│   OpenCode   │───────────────▶│  Mysterium Node   │──────────────▶│ Residential   │
│  (plugin)    │  (loopback)    │  (--proxymode)    │  (userspace)  │ exit IP       │
└──────────────┘                └───────────────────┘               └───────────────┘
                                        │
                                   timer fires
                                        ▼
                                  rotate() → new exit
```

1. The `myst` node (Docker) runs in its **own network namespace** with `--proxymode`,
   exposing a local HTTP proxy on a loopback port plus TequilAPI on `127.0.0.1:4050`.
2. `myst-rotator connect` picks a residential node and brings up a userspace WireGuard
   tunnel to it.
3. The plugin points `HTTP_PROXY`/`HTTPS_PROXY`/`ALL_PROXY` at that local proxy, so
   OpenCode's provider calls leave through the residential IP. **Your own traffic is
   never routed** — only what uses the proxy.
4. A timer rotates to a fresh exit (default every 10 min), so an IP-scoped rate limit
   is never reached. `/myst` rotates immediately.
5. `myst-rotator serve` is the loopback control socket the plugin uses to read status
   and trigger rotations.

---

## OpenCode Integration

The plugin (`opencode-plugin/`) routes **all** OpenCode model traffic through the
Mysterium residential exit and rotates that exit **on a timer**, so IP-scoped
rate limits are avoided rather than hit.

### Install

```bash
# 1. Symlink the plugin into OpenCode's plugin directory
mkdir -p ~/.config/opencode/plugins
ln -sfn "$PWD/opencode-plugin" ~/.config/opencode/plugins/myst-rotator

# 2. Start the control socket the plugin talks to
myst-rotator serve &
```

### Verify

```bash
# Model traffic now leaves through the residential exit, not your ISP
curl -s -x http://127.0.0.1:$(myst-rotator status | grep -oP '"proxy": "\K[^"]+' | grep -oP ':\K[0-9]+') https://ipinfo.io/json
```

Then start OpenCode. On load you should see:

```
[myst-rotator] Routing through 94.154.102.62 (PL) via http://127.0.0.1:40815
[myst-rotator] Auto-rotation every 10 min
```

And each time the timer fires:

```
[myst-rotator] timer: now 185.22.152.1 (NL) via http://127.0.0.1:40817
```

### Configuration

Rotation interval and control socket can be set either way (plugin options win):

```jsonc
// ~/.config/opencode/opencode.json
{
  "plugin": [["myst-rotator", { "rotateEveryMin": 5 }]]
}
```

```bash
# or via environment
export MYST_ROTATOR_EVERY_MIN=5        # minutes between rotations (0 = off)
export MYST_ROTATOR_CONTROL=http://127.0.0.1:8787
```

Default is 10 minutes. Lower it if your provider's IP limit is tight; raise it if
you want fewer session changes. Set `0` to disable the timer and rotate manually.

### Why a timer instead of reacting to 429

Verified against the live OpenCode plugin runtime (v2 API). At setup time the
available domains are:

```
options, agent, aisdk, catalog, command, integration, plugin, reference, skill
```

There is **no `session` domain and no `retry` hook** (`ctx.session` is `undefined`),
so a plugin **cannot** catch a 429 and re-issue the request. Upstream
`opencode-tunnel-switch` relies on `ctx.session.hook("retry", ...)`, which only
exists in builds that expose it — copying that design would silently do nothing.

Rotating on a timer is the correct answer anyway: for an IP-scoped limit you get a
fresh IP *before* the limit is reached, so the 429 never happens. Run `/myst` in
any session to rotate immediately.

### Tests

```bash
python3 tests/test_plugin_timer.py
```

Loads the real plugin against a mock control socket and asserts the timer fires,
the exit changes, and the proxy env is re-pointed — no funded identity required.

### Rate limits worth knowing

Two different kinds, and only one is fixed by rotating IPs:

| Where | 429 cause | Fixed by rotating IP? |
|---|---|---|
| OpenCode free models (`opencode/...-free`) | IP-based rate limit | **Yes** |
| AntSeed free models (`antseed/...-free`) | Account/stake-based (`free_tier_exhausted`) | **No** — needs a stake, not a new IP |

If a 429 body says `free_tier_exhausted` and mentions staking ANTS, that is an
account limit. A new residential IP will not help; stake tokens in that
seller's pool instead.

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

## The registration bug (why `myst-rotator register` exists)

Mysterium identity registration is handled by a **transactor service** that signs and
submits a transaction on your behalf. This service frequently fails and leaves
identities stuck `InProgress` forever — it is a known, open bug:
[mysteriumnetwork/node#6190](https://github.com/mysteriumnetwork/node/issues/6190)
(reproduced May–Oct 2026, still unfixed; verified on multiple fresh identities).

The on-chain `Registry.registerIdentity()` has a second, subtler bug: it checks the
**channel's** MYST balance *before* the channel contract is deployed:

```solidity
require(_totalFee <= token.balanceOf(getChannelAddress(_identity, _hermesId)),
    "Registry: not enough funds in channel to cover fees");  // reverts: channel has no code yet
_openChannel(_identity, _hermesId, _beneficiary, _totalFee);  // deploys the channel
```

`getChannelAddress()` is deterministic, but `balanceOf()` there is 0 until the
contract exists — so direct registration always reverts.

**The fix** (`myst-rotator register`): pre-fund the channel address with MYST
*before* calling `registerIdentity()`, then submit the transactor-signed transaction
directly on-chain with [`cast`](https://getfoundry.sh):

1. Trigger the node's registration → the transactor signs the request
2. Capture the signature + fee from the node's own logs
3. Send ~1 MYST to the deterministic channel address (so the balance check passes)
4. Submit `registerIdentity(...)` directly to the Registry contract

Verified working on Polygon mainnet: identity registered, channel funded, ~0.928 MYST
left after the transactor fee.

---

## VPN / P2P note

The node needs direct UDP for its DHT/P2P layer. On a host with a **system-wide
kill-switch VPN** (Mullvad lockdown mode, for example) outbound UDP from the
container is dropped by the firewall, and P2P dials fail with
`p2p dialer failed` / `too few connections were built`.

Two ways to handle it, in order of preference:

1. **Recommended — no changes needed.** This project runs the node in its own
   network namespace with `--proxymode`, so nothing touches your host's routing
   table. Only the plugin's proxy traffic is affected by your VPN, and only if
   your VPN blocks the residential exit's port.
2. **If P2P dials still fail**, allow the `myst` container outside the VPN
   (`mullvad split-tunnel add <pid>`, or your VPN's split-tunnel setting), or
   pause the VPN while connecting. This is a host-specific workaround, never a
   requirement for other users.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Connection refused` | Start the node: `myst-rotator up` |
| `No identity` | Run: `myst-rotator identity` |
| `insufficient balance` | Send MYST + POL to your identity on Polygon |
| `registration InProgress` | Needs POL for gas. Send ~0.1 POL on Polygon |
| `no residential proposals` | Try another country: `myst-rotator connect --country US` |
| `p2p dialer failed` / `too few connections` | See "VPN / P2P note" above |
| `/myst` says rotate failed | Check the node is up and funded: `myst-rotator status` |
| Plugin logs no routing line | No active session — run `myst-rotator connect`, then restart OpenCode |
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