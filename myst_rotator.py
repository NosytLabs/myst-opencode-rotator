#!/usr/bin/env python3
"""
Mysterium IP Rotator for OpenCode

Rotates residential IPs via Mysterium Network (myst node) to avoid
free-tier rate limits on AI coding services.

Requires:
  - Mysterium node running in consumer mode (Docker)
  - MYST tokens + a little POL (Polygon gas) in the identity wallet
  - cast (Foundry) for the registration workaround:
      curl -L https://foundry.paradigm.xyz | bash && foundryup

Registration note (GitHub issue mysteriumnetwork/node#6190):
  The Mysterium transactor often fails to submit identity registration
  on-chain, leaving identities stuck "InProgress" forever. This tool
  works around it: pre-fund the deterministic channel address with MYST,
  then submit registerIdentity() directly on-chain using the transactor's
  signature (captured from the node's own registration attempt).

Usage:
  myst-rotator setup                     # Full guided setup (create id, fund, register)
  myst-rotator register                  # Register identity (workaround)
  myst-rotator connect [--country DE]    # Connect to residential IP
  myst-rotator rotate                    # Rotate to a new random country
  myst-rotator disconnect                # Disconnect
  myst-rotator status                    # Show current connection
  myst-rotator ip                        # Show current public IP
  myst-rotator proposals [--country US]  # List available residential nodes
  myst-rotator balance                   # Show MYST balance (wallet + channel)
  myst-rotator identity                  # Show identity address
  myst-rotator daemon [--interval 600]   # Auto-rotate every N seconds
"""

import argparse
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = os.environ.get("MYST_API", "http://127.0.0.1:4050")
MYST_CHAIN_ID = 137

# Mysterium mainnet contracts (Polygon)
REGISTRY = os.environ.get("MYST_REGISTRY", "0x87F0F4b7e0FAb14A565C87BAbbA6c40c92281b51")
HERMES = os.environ.get("MYST_HERMES", "0x80Ed28d84792d8b153bf2F25F0C4B7a1381dE4ab")
MYST_TOKEN = os.environ.get("MYST_TOKEN", "0x1379e8886a944d2d9d440b3d88df536aea08d9f3")
RPC_URL = os.environ.get("MYST_RPC", "https://polygon1.mysterium.network/")

CONFIG_DIR = Path.home() / ".config" / "myst-rotator"
LOG_FILE = CONFIG_DIR / "rotator.log"
PID_FILE = CONFIG_DIR / "daemon.pid"
IDENTITY_FILE = CONFIG_DIR / "identity.txt"
PASSPHRASE_FILE = CONFIG_DIR / "passphrase.txt"  # 0600

# MYST to pre-fund the channel before registerIdentity (covers the transactor fee ~0.072 MYST)
CHANNEL_FUND_MYST = float(os.environ.get("MYST_CHANNEL_FUND", "1"))
DEFAULT_GAS_GWEI = os.environ.get("MYST_GAS_GWEI", "300")

PREFERRED_COUNTRIES = [
    "US", "DE", "GB", "FR", "NL", "CA", "RO", "TR",
    "ES", "IN", "AU", "SG", "IT", "CH", "JP", "BR",
    "MX", "PL", "SE", "NO",
]


def ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    ensure_config_dir()
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    print(line, file=sys.stderr)


def api(method: str, path: str, data=None, timeout: int = 30):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return json.loads(raw)
        except Exception:
            return {"error": {"message": raw, "status": e.code}}
    except Exception as e:
        return {"error": {"message": str(e)}}


def get_public_ip() -> str:
    for url in ("https://ifconfig.me", "https://icanhazip.com", "https://ipinfo.io/ip"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                ip = resp.read().decode().strip()
                if ip and len(ip) < 50:
                    return ip
        except Exception:
            continue
    return "unknown"


def check_node() -> bool:
    try:
        result = api("GET", "/healthcheck")
        return "uptime" in result
    except Exception:
        return False


def get_passphrase() -> str:
    if PASSPHRASE_FILE.exists():
        return PASSPHRASE_FILE.read_text().strip()
    return "myst-rotator"


def save_passphrase(passphrase: str):
    ensure_config_dir()
    PASSPHRASE_FILE.write_text(passphrase)
    PASSPHRASE_FILE.chmod(0o600)


def get_identity() -> str | None:
    if IDENTITY_FILE.exists():
        saved = IDENTITY_FILE.read_text().strip()
        if saved:
            return saved
    result = api("GET", "/identities")
    if isinstance(result, dict) and result.get("identities"):
        identity_id = result["identities"][0]["id"]
        ensure_config_dir()
        IDENTITY_FILE.write_text(identity_id)
        return identity_id
    return None


def create_identity(passphrase: str) -> str | None:
    result = api("POST", "/identities", {"passphrase": passphrase})
    if "error" in result:
        log(f"Failed to create identity: {result['error']}")
        return None
    identity_id = result.get("id")
    if identity_id:
        save_passphrase(passphrase)
        ensure_config_dir()
        IDENTITY_FILE.write_text(identity_id)
    return identity_id


def unlock_identity(identity_id: str) -> bool:
    result = api("PUT", f"/identities/{identity_id}/unlock", {"passphrase": get_passphrase()})
    return "error" not in result


def get_identity_info(identity_id: str) -> dict:
    result = api("GET", f"/identities/{identity_id}")
    if "error" in result:
        return {"error": result["error"]}
    return result


def get_balance(identity_id: str) -> dict:
    info = get_identity_info(identity_id)
    if "error" in info:
        return {"error": info["error"]}
    return {
        "balance_myst": info.get("balance_tokens", {}).get("human", "0"),
        "registration_status": info.get("registration_status", "unknown"),
        "channel_address": info.get("channel_address", ""),
        "hermes_id": info.get("hermes_id", ""),
    }


def get_connection_status() -> dict:
    result = api("GET", "/connection")
    if "error" in result:
        return {"connected": False, "error": result["error"]}
    loc = result.get("location") or {}
    return {
        "connected": result.get("status") == "Connected",
        "consumer_id": result.get("consumer_id"),
        "provider_id": result.get("provider_id"),
        "country": loc.get("country"),
        "ip": result.get("ip"),
    }


def get_proposals(country=None) -> list:
    path = "/proposals?ip_type=residential"
    if country:
        path += f"&country_code={country}"
    result = api("GET", path)
    if isinstance(result, dict) and "proposals" in result:
        return result["proposals"]
    elif isinstance(result, list):
        return result
    return []


# ---------------------------------------------------------------------------
# Registration workaround (mysteriumnetwork/node#6190)
# ---------------------------------------------------------------------------

def require_cast() -> bool:
    cast = shutil.which("cast") or os.path.expanduser("~/.foundry/bin/cast")
    if not cast:
        log("ERROR: 'cast' (Foundry) not found. Install: "
            "curl -L https://foundry.paradigm.xyz | bash && foundryup")
        return False
    return True


def _cast_bin() -> str:
    return shutil.which("cast") or os.path.expanduser("~/.foundry/bin/cast")


def _keystore_path(identity_id: str) -> Path | None:
    """Locate the node's keystore file for an identity (docker volume)."""
    candidates = []
    # Docker container default path
    try:
        out = subprocess.run(
            ["docker", "exec", "myst", "find", "/var/lib/mysterium-node/keystore/",
             "-name", f"*{identity_id[2:]}*", "-type", "f"],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            candidates.append(out.stdout.strip())
    except Exception:
        pass
    for c in candidates:
        if c:
            dest = CONFIG_DIR / f"keystore-{identity_id[:10]}.json"
            try:
                subprocess.run(["docker", "cp", f"myst:{c}", str(dest)],
                               capture_output=True, timeout=10)
                if dest.exists():
                    return dest
            except Exception:
                continue
    return None


def _trigger_transactor_signature(identity_id: str) -> str | None:
    """Ask the node to register (triggers transactor signing), then capture
    the signature from the node logs. Returns the signature hex or None."""
    # Trigger registration attempt (the node signs the request via transactor)
    api("PUT", f"/identities/{identity_id}/unlock", {"passphrase": get_passphrase()})
    api("POST", f"/identities/{identity_id}/register",
        {"beneficiary": identity_id})
    # Give the node a moment to call the transactor and log the signature
    time.sleep(4)
    try:
        out = subprocess.run(["docker", "logs", "--tail", "50", "myst"],
                             capture_output=True, text=True, timeout=15)
        text = out.stdout + out.stderr
        m = re.search(r"transactor_identity_registration.*?Identity:(" + re.escape(identity_id) + r").*?Signature:(0x[0-9a-fA-F]+)", text)
        if not m:
            # Fields can be in any order - find the line mentioning our identity
            for line in text.splitlines():
                if "transactor_identity_registration" in line and identity_id.lower() in line.lower():
                    sm = re.search(r"Signature:(0x[0-9a-fA-F]+)", line)
                    if sm:
                        return sm.group(1)
        else:
            return m.group(2)
    except Exception as e:
        log(f"Could not read docker logs: {e}")
    return None


def _transfer_myst(to_address: str, amount_tokens: float, keystore: Path,
                   passphrase: str) -> bool:
    """Send MYST from the identity wallet to the channel address."""
    amount_wei = int(amount_tokens * 1e18)
    gas_gwei = os.environ.get("MYST_GAS_GWEI", DEFAULT_GAS_GWEI)
    cmd = [
        _cast_bin(), "send", MYST_TOKEN, "transfer(address,uint256)",
        to_address, str(amount_wei),
        "--rpc-url", RPC_URL,
        "--keystore", str(keystore),
        "--password", passphrase,
        "--gas-limit", "100000",
        "--gas-price", str(int(gas_gwei) * 10**9),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if "status" in r.stdout and "0 (failed)" not in r.stdout:
            return True
        # status 1 (success) shows as "1 (success)"
        if "1 (success)" in r.stdout or "status1" in r.stdout.replace(" ", ""):
            return True
        log(f"MYST transfer output: {r.stdout[-300:]} {r.stderr[-200:]}")
    except Exception as e:
        log(f"MYST transfer failed: {e}")
    return False


def _register_onchain(identity_id: str, keystore: Path, passphrase: str,
                      signature: str, fee: str) -> bool:
    """Call registerIdentity on the Registry contract directly."""
    gas_gwei = os.environ.get("MYST_GAS_GWEI", DEFAULT_GAS_GWEI)
    cmd = [
        _cast_bin(), "send", REGISTRY,
        "registerIdentity(address,uint256,uint256,address,bytes)",
        HERMES, "0", fee, identity_id, signature,
        "--rpc-url", RPC_URL,
        "--keystore", str(keystore),
        "--password", passphrase,
        "--gas-limit", "500000",
        "--gas-price", str(int(gas_gwei) * 10**9),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        out = r.stdout + r.stderr
        if "1 (success)" in out or ("status" in out and "0 (failed)" not in out):
            return True
        log(f"registerIdentity failed: {out[-400:]}")
    except Exception as e:
        log(f"registerIdentity error: {e}")
    return False


def _get_transactor_fee() -> str | None:
    """Capture the transactor fee from a registration event in the logs."""
    try:
        out = subprocess.run(["docker", "logs", "--tail", "50", "myst"],
                             capture_output=True, text=True, timeout=15)
        text = out.stdout + out.stderr
        m = re.search(r"transactor_identity_registration.*?Fee:\+(\d+)", text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def register_identity(identity_id: str) -> bool:
    """Register an identity on-chain, working around the stuck transactor.

    Steps (the fix for mysteriumnetwork/node#6190):
      1. Trigger the node's registration -> transactor signs the request
      2. Capture signature + fee from node logs
      3. Pre-fund the deterministic channel address with MYST (the Registry
         checks the channel balance BEFORE the channel contract is deployed,
         so the tokens must be sent to the channel address first)
      4. Submit registerIdentity() directly on-chain
    """
    if not require_cast():
        return False

    info = get_identity_info(identity_id)
    if "error" in info:
        log(f"Identity not found: {info['error']}")
        return False

    if info.get("registration_status") == "Registered":
        print(f"Identity {identity_id} is already registered.")
        return True

    keystore = _keystore_path(identity_id)
    if not keystore:
        log("ERROR: Could not locate the identity keystore in the myst container.")
        return False

    passphrase = get_passphrase()

    # 1+2. Trigger registration and capture signature + fee from node logs
    log("Requesting transactor signature...")
    signature = _trigger_transactor_signature(identity_id)
    fee = _get_transactor_fee()
    if not signature:
        log("ERROR: Could not capture transactor signature from node logs. "
            "Is the myst container running? (docker ps | grep myst)")
        return False
    if not fee:
        log("WARNING: Could not read transactor fee; assuming 0 (self-register path).")
        fee = "0"
    log(f"Signature captured. Fee: {int(fee)/1e18:.4f} MYST")

    # 3. Pre-fund the channel address (the bug: channel must hold MYST before it exists)
    channel = info.get("channel_address", "")
    if not channel:
        log("ERROR: No channel address reported by the node.")
        return False
    log(f"Pre-funding channel {channel} with {CHANNEL_FUND_MYST} MYST...")
    if not _transfer_myst(channel, CHANNEL_FUND_MYST, keystore, passphrase):
        log("ERROR: Failed to fund the channel. Does the wallet have MYST + POL?")
        return False

    # 4. Register on-chain
    log("Submitting registerIdentity on-chain...")
    if not _register_onchain(identity_id, keystore, passphrase, signature, fee):
        return False

    # Verify
    info2 = get_identity_info(identity_id)
    if info2.get("registration_status") == "Registered":
        print(f"Identity {identity_id} registered on-chain. Channel: {channel}")
        return True
    log(f"Registration submitted but status is {info2.get('registration_status')}. "
        "Check the node in a minute.")
    return True


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def connect_to(country=None, identity_id=None) -> bool:
    if not check_node():
        log("ERROR: Myst node not running. Start it: docker start myst")
        return False

    identity_id = identity_id or get_identity()
    if not identity_id:
        log("ERROR: No identity. Run: myst-rotator setup")
        return False

    if not unlock_identity(identity_id):
        log("WARNING: Could not unlock identity (may already be unlocked)")

    proposals = get_proposals(country)
    if not proposals:
        log(f"No residential proposals available" + (f" in {country}" if country else ""))
        return False

    proposals.sort(key=lambda p: p.get("quality", {}).get("quality", 0), reverse=True)
    proposal = random.choice(proposals[:5])

    provider_id = proposal["provider_id"]
    location = proposal.get("location", {})
    prop_country = location.get("country", "?")
    prop_isp = location.get("isp", "?")
    price_gib = proposal.get("price", {}).get("per_gib_tokens", {}).get("human", "?")

    log(f"Connecting to {prop_country} ({prop_isp}), {price_gib} MYST/GiB, provider {provider_id[:20]}...")

    result = api("PUT", "/connection", {
        "consumer_id": identity_id,
        "provider_id": provider_id,
        "service_type": "wireguard",
    })

    if "error" in result:
        msg = result["error"].get("message", "unknown")
        log(f"Connect failed: {msg}")
        if "p2p" in msg.lower() or "dial" in msg.lower():
            log("Hint: P2P dial failures are usually the host VPN (Mullvad) blocking "
                "UDP or DNS. Allow the myst node outside the VPN, or retry.")
        return False
    time.sleep(5)
    status = get_connection_status()
    if status.get("connected"):
        ip = get_public_ip()
        log(f"Connected! IP: {ip} (country: {prop_country}, ISP: {prop_isp})")
        return True
    else:
        log(f"Connection pending. Status: {status}")
        return True


def disconnect() -> bool:
    if not check_node():
        log("ERROR: Myst node not running")
        return False
    log("Disconnecting...")
    result = api("DELETE", "/connection")
    if "error" in result:
        log(f"Disconnect failed: {result['error'].get('message', 'unknown')}")
        return False
    log("Disconnected.")
    return True


def rotate() -> bool:
    old_status = get_connection_status()
    old_country = old_status.get("country")
    old_ip = get_public_ip()

    disconnect()
    time.sleep(2)

    candidates = [c for c in PREFERRED_COUNTRIES if c != old_country]
    random.shuffle(candidates)

    for country in candidates[:5]:
        log(f"Trying country: {country}")
        if connect_to(country=country):
            new_ip = get_public_ip()
            if new_ip != old_ip and new_ip != "unknown":
                log(f"Rotation successful: {old_ip} -> {new_ip} (country: {country})")
                return True
            elif new_ip != "unknown":
                log(f"Connected to {country} but IP unchanged ({new_ip}). Trying next...")
                disconnect()
                time.sleep(2)
            else:
                log(f"Connected to {country} but couldn't verify IP. Assuming success.")
                return True

    log("All rotation attempts failed.")
    return False


def cmd_setup(args):
    """Guided end-to-end setup: create identity -> fund -> register."""
    print("=== Mysterium IP Rotator setup ===\n")

    if not check_node():
        print("ERROR: The myst node is not running (TequilAPI unreachable at "
              f"{API_BASE}).\nStart it with:\n  docker start myst")
        sys.exit(1)

    identity_id = get_identity()
    if not identity_id:
        print("Creating a new identity...")
        passphrase = "myst-rotator"
        if not args.yes:
            try:
                passphrase = input("Identity passphrase [myst-rotator]: ").strip() or "myst-rotator"
            except EOFError:
                passphrase = "myst-rotator"
        identity_id = create_identity(passphrase)
        if not identity_id:
            print("Failed to create identity.", file=sys.stderr)
            sys.exit(1)
        print(f"Identity created: {identity_id}")
    else:
        print(f"Using identity: {identity_id}")

    bal = get_balance(identity_id)
    print(f"Registration: {bal.get('registration_status', '?')}")
    print(f"MYST balance: {bal.get('balance_myst', '?')}")

    if bal.get("registration_status") != "Registered":
        print(f"\nTo register, send MYST + POL (Polygon network) to:\n  {identity_id}")
        print(f"Recommended: ~{CHANNEL_FUND_MYST + 1} MYST (~$0.60) + ~0.5 POL (~$0.04)")
        if not args.yes:
            try:
                input("\nPress Enter once funded (or Ctrl+C to abort)...")
            except EOFError:
                pass
        if not register_identity(identity_id):
            print("\nRegistration failed. Common causes:", file=sys.stderr)
            print("  - Not enough MYST in the wallet (needs >= ~1 MYST + fee)", file=sys.stderr)
            print("  - Not enough POL for gas", file=sys.stderr)
            print("  - Transactor signature not captured (is 'docker logs myst' readable?)", file=sys.stderr)
            sys.exit(1)

    print("\nSetup complete. Connect with: myst-rotator connect")


def cmd_register(args):
    identity_id = args.identity or get_identity()
    if not identity_id:
        print("No identity. Run: myst-rotator setup", file=sys.stderr)
        sys.exit(1)
    ok = register_identity(identity_id)
    print("Registration OK." if ok else "Registration failed.", file=sys.stderr)
    sys.exit(0 if ok else 1)


def cmd_connect(args):
    country = args.country or random.choice(PREFERRED_COUNTRIES)
    if connect_to(country=country):
        ip = get_public_ip()
        print(f"Connected to residential IP: {ip} (country: {country})")
    else:
        print("Failed to connect. Check: myst-rotator balance", file=sys.stderr)
        sys.exit(1)


def cmd_rotate(args):
    if rotate():
        print("Rotation successful.")
    else:
        print("Rotation failed. Check: myst-rotator status", file=sys.stderr)
        sys.exit(1)


def cmd_disconnect(args):
    if disconnect():
        print("Disconnected.")
    else:
        sys.exit(1)


def cmd_status(args):
    status = get_connection_status()
    ip = get_public_ip()
    identity_id = get_identity()
    balance = get_balance(identity_id) if identity_id else {}
    output = {
        "connected": status.get("connected", False),
        "country": status.get("country"),
        "provider_id": status.get("provider_id"),
        "public_ip": ip,
        "identity": identity_id,
        "balance_myst": balance.get("balance_myst", "?"),
        "registration": balance.get("registration_status", "?"),
    }
    print(json.dumps(output, indent=2))


def cmd_ip(args):
    print(get_public_ip())


def cmd_proposals(args):
    proposals = get_proposals(args.country)
    if not proposals:
        print(f"No residential proposals" + (f" in {args.country}" if args.country else "") + ".")
        return
    print(f"Available residential nodes ({len(proposals)}):")
    proposals.sort(key=lambda p: p.get("quality", {}).get("quality", 0), reverse=True)
    for p in proposals[:20]:
        loc = p.get("location", {})
        price = p.get("price", {}).get("per_gib_tokens", {}).get("human", "?")
        quality = p.get("quality", {}).get("quality", "?")
        print(f"  {loc.get('country','?'):3s} {loc.get('city','?'):15s} | {price:>8s} MYST/GiB | Q:{quality} | {p['provider_id'][:20]}...")


def cmd_balance(args):
    identity_id = get_identity()
    if not identity_id:
        print("No identity found. Run: myst-rotator setup")
        sys.exit(1)

    balance = get_balance(identity_id)
    print(f"Identity:     {identity_id}")
    print(f"Channel:      {balance.get('channel_address', '?')}")
    print(f"Balance:      {balance.get('balance_myst', '?')} MYST")
    print(f"Registration: {balance.get('registration_status', '?')}")
    print(f"\nTo add MYST + POL gas, send them (on Polygon) to:")
    print(f"  {identity_id}")


def cmd_identity(args):
    identity_id = get_identity()
    if identity_id:
        print(identity_id)
    else:
        print("No identity. Run: myst-rotator setup", file=sys.stderr)
        sys.exit(1)


def cmd_daemon(args):
    interval = args.interval or 600
    ensure_config_dir()

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    def cleanup(signum, frame):
        log("Daemon stopping (signal received).")
        if PID_FILE.exists():
            PID_FILE.unlink()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    log(f"Daemon started (interval: {interval}s, PID: {os.getpid()})")

    conn_status = get_connection_status()
    if not conn_status.get("connected"):
        rotate()

    try:
        while True:
            time.sleep(interval)
            log(f"Scheduled rotation (every {interval}s)")
            rotate()
    except KeyboardInterrupt:
        log("Daemon stopped by user.")
    finally:
        if PID_FILE.exists():
            PID_FILE.unlink()


def cmd_daemon_status(args):
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            print(f"Daemon running (PID: {pid})")
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            print("Daemon not running (stale PID file).")
            sys.exit(1)
    else:
        print("Daemon not running.")
        sys.exit(1)


def cmd_daemon_stop(args):
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Daemon stopped (PID: {pid}).")
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.5)
                except ProcessLookupError:
                    break
            if PID_FILE.exists():
                PID_FILE.unlink()
            sys.exit(0)
        except (ProcessLookupError, ValueError):
            print("Daemon not running (stale PID file).")
            if PID_FILE.exists():
                PID_FILE.unlink()
            sys.exit(1)
    else:
        print("Daemon not running.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Mysterium IP Rotator for OpenCode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("setup", help="Guided setup (create identity, fund, register)")
    p.add_argument("--yes", "-y", action="store_true", help="Non-interactive (defaults)")
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("register", help="Register identity on-chain (transactor workaround)")
    p.add_argument("--identity", "-i", help="Identity address (default: saved)")
    p.set_defaults(func=cmd_register)

    p = sub.add_parser("connect", help="Connect to residential IP")
    p.add_argument("--country", "-c", help="Country code (e.g. US, DE, FR)")
    p.set_defaults(func=cmd_connect)

    p = sub.add_parser("rotate", help="Rotate to a new residential IP")
    p.set_defaults(func=cmd_rotate)

    p = sub.add_parser("disconnect", help="Disconnect from VPN")
    p.set_defaults(func=cmd_disconnect)

    p = sub.add_parser("status", help="Show connection status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("ip", help="Show current public IP")
    p.set_defaults(func=cmd_ip)

    p = sub.add_parser("proposals", help="List available residential nodes")
    p.add_argument("--country", "-c", help="Filter by country code")
    p.set_defaults(func=cmd_proposals)

    p = sub.add_parser("balance", help="Show MYST balance")
    p.set_defaults(func=cmd_balance)

    p = sub.add_parser("identity", help="Show/create identity address")
    p.set_defaults(func=cmd_identity)

    p = sub.add_parser("daemon", help="Run auto-rotation daemon")
    p.add_argument("--interval", "-i", type=int, default=600, help="Rotation interval in seconds (default: 600)")
    p.set_defaults(func=cmd_daemon)

    p = sub.add_parser("daemon-status", help="Check daemon status")
    p.set_defaults(func=cmd_daemon_status)

    p = sub.add_parser("daemon-stop", help="Stop the daemon")
    p.set_defaults(func=cmd_daemon_stop)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()