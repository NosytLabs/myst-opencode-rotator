#!/usr/bin/env python3
"""
Mysterium IP Rotator for OpenCode

Rotates residential IPs via Mysterium Network (myst node) to avoid
free-tier rate limits on AI coding services.

Requires:
  - Mysterium node running in consumer mode (Docker or native)
  - MYST tokens + a little POL (Polygon gas) in the identity wallet

Usage:
  myst-rotator connect [--country DE]    # Connect to residential IP
  myst-rotator rotate                    # Rotate to a new random country
  myst-rotator disconnect                # Disconnect
  myst-rotator status                    # Show current connection
  myst-rotator ip                        # Show current public IP
  myst-rotator proposals [--country US]  # List available residential nodes
  myst-rotator balance                   # Show MYST balance
  myst-rotator identity                  # Show identity address
  myst-rotator daemon [--interval 600]   # Auto-rotate every N seconds
"""

import argparse
import json
import os
import random
import signal
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

API_BASE = os.environ.get("MYST_API", "http://127.0.0.1:4050")

CONFIG_DIR = Path.home() / ".config" / "myst-rotator"
LOG_FILE = CONFIG_DIR / "rotator.log"
PID_FILE = CONFIG_DIR / "daemon.pid"
IDENTITY_FILE = CONFIG_DIR / "identity.txt"

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


def get_identity():
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


def unlock_identity(identity_id: str) -> bool:
    result = api("PUT", f"/identities/{identity_id}/unlock", {"passphrase": "myst-rotator"})
    return "error" not in result


def get_balance(identity_id: str) -> dict:
    result = api("GET", f"/identities/{identity_id}")
    if "error" in result:
        return {"error": result["error"]}
    return {
        "balance_myst": result.get("balance_tokens", {}).get("human", "0"),
        "registration_status": result.get("registration_status", "unknown"),
        "channel_address": result.get("channel_address", ""),
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


def connect_to(country=None, identity_id=None) -> bool:
    if not check_node():
        log("ERROR: Myst node not running. Start it: docker start myst")
        return False

    identity_id = identity_id or get_identity()
    if not identity_id:
        log("ERROR: No identity. Create one: myst-rotator identity")
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
        log(f"Connect failed: {result['error'].get('message', 'unknown')}")
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
        print("No identity found. Creating one...")
        result = api("POST", "/identities", {"passphrase": "myst-rotator"})
        if "id" in result:
            identity_id = result["id"]
            ensure_config_dir()
            IDENTITY_FILE.write_text(identity_id)
            print(f"Identity created: {identity_id}")
        else:
            print(f"Failed to create identity: {result}", file=sys.stderr)
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
        result = api("POST", "/identities", {"passphrase": "myst-rotator"})
        if "id" in result:
            identity_id = result["id"]
            ensure_config_dir()
            IDENTITY_FILE.write_text(identity_id)
            print(f"Identity created: {identity_id}")
            print(f"Send MYST + POL (on Polygon) to this address.")
        else:
            print(f"Failed: {result}", file=sys.stderr)
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