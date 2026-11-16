#!/usr/bin/env python3
"""
Mysterium IP Rotator for OpenCode

Rotates residential IPs via Mysterium VPN (mystvpn CLI) to avoid
free-tier rate limits on AI coding services.

Usage:
  myst-rotator connect [--country DE]    # Connect to residential IP
  myst-rotator rotate                    # Rotate to a new random country
  myst-rotator disconnect                # Disconnect
  myst-rotator status                    # Show current connection
  myst-rotator ip                        # Show current public IP
  myst-rotator countries                 # List available countries
  myst-rotator daemon [--interval 600]   # Auto-rotate every N seconds
"""

import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

MYSTVPN = shutil.which("mystvpn") or "/usr/bin/mystvpn"
CONFIG_DIR = Path.home() / ".config" / "myst-rotator"
LOG_FILE = CONFIG_DIR / "rotator.log"
PID_FILE = CONFIG_DIR / "daemon.pid"

# Countries with the most residential nodes (by server count, descending)
PREFERRED_COUNTRIES = [
    "US",   # USA - 3204 servers
    "DE",   # Germany - 1190 servers
    "GB",   # UK - 910 servers (note: mystvpn uses GB, not UK)
    "FR",   # France - 812 servers
    "NL",   # Netherlands - 531 servers
    "CA",   # Canada - 454 servers
    "RO",   # Romania - 311 servers
    "TR",   # Turkey - 307 servers
    "ES",   # Spain - 218 servers
    "IN",   # India - 207 servers
    "AU",   # Australia - 204 servers
    "SG",   # Singapore - 203 servers
    "IT",   # Italy - 195 servers
    "CH",   # Switzerland - 149 servers
    "JP",   # Japan - 117 servers
    "BR",   # Brazil
    "MX",   # Mexico
    "PL",   # Poland
    "SE",   # Sweden
    "NO",   # Norway
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


def run(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a command with timeout."""
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def get_public_ip() -> str:
    """Get current public IP."""
    for url in ("https://ifconfig.me", "https://icanhazip.com", "https://ipinfo.io/ip"):
        try:
            r = run(["curl", "-s", "--max-time", "5", url], timeout=8)
            ip = r.stdout.strip()
            if ip and len(ip) < 50:
                return ip
        except Exception:
            continue
    return "unknown"


def check_mystvpn() -> bool:
    """Check if mystvpn is installed."""
    if not os.path.exists(MYSTVPN):
        log("ERROR: mystvpn not found. Install: curl -fsSL https://github.com/mysteriumnetwork/mysteriumvpncli/releases/latest/download/install.sh | bash")
        return False
    return True


def myst_status() -> dict:
    """Get mystvpn connection status."""
    if not check_mystvpn():
        return {"error": "mystvpn not installed"}
    try:
        r = run([MYSTVPN, "status"], timeout=10)
        output = r.stdout.strip()
        # mystvpn status outputs "Connected:  yes" or "Connected:  no"
        connected = "connected:" in output.lower() and "yes" in output.lower()
        return {"connected": connected, "country": None, "raw": output}
    except Exception as e:
        return {"error": str(e), "connected": False}


def is_connected() -> bool:
    return myst_status().get("connected", False)


def myst_connect(country: str | None = None, ip_type: str = "residential") -> bool:
    """Connect to Mysterium VPN."""
    if not check_mystvpn():
        return False
    cmd = [MYSTVPN, "connect", "--ip-type", ip_type]
    if country:
        cmd.extend(["--country", country])
    log(f"Connecting: {' '.join(cmd)}")
    try:
        r = run(cmd, timeout=60)
        if r.returncode == 0:
            time.sleep(3)  # Wait for WireGuard handshake
            ip = get_public_ip()
            log(f"Connected. Public IP: {ip}")
            return True
        else:
            log(f"Connect failed: {r.stderr.strip()[:200]}")
            return False
    except subprocess.TimeoutExpired:
        log("Connect timed out (WireGuard handshake may be slow)")
        return False
    except Exception as e:
        log(f"Connect error: {e}")
        return False


def myst_disconnect() -> bool:
    """Disconnect from Mysterium VPN."""
    if not check_mystvpn():
        return False
    log("Disconnecting...")
    try:
        r = run([MYSTVPN, "disconnect"], timeout=15)
        if r.returncode == 0:
            log("Disconnected.")
            return True
        else:
            log(f"Disconnect failed: {r.stderr.strip()[:200]}")
            return False
    except Exception as e:
        log(f"Disconnect error: {e}")
        return False


def get_countries() -> list[str]:
    """Get available residential countries."""
    if not check_mystvpn():
        return PREFERRED_COUNTRIES
    try:
        r = run([MYSTVPN, "countries", "--ip-type", "residential"], timeout=15)
        if r.returncode == 0:
            countries = []
            for line in r.stdout.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # mystvpn may output "US, United States" or just "US"
                parts = line.split(",")
                code = parts[0].strip().upper()
                if len(code) <= 3 and code.isalpha():
                    countries.append(code)
            return countries if countries else PREFERRED_COUNTRIES
    except Exception:
        pass
    return PREFERRED_COUNTRIES


def rotate() -> bool:
    """Rotate to a new residential IP in a different country."""
    old_ip = get_public_ip()
    old_status = myst_status()
    old_country = old_status.get("country")

    # Disconnect first
    myst_disconnect()
    time.sleep(2)

    # Try preferred countries (excluding current)
    candidates = [c for c in PREFERRED_COUNTRIES if c != old_country]
    random.shuffle(candidates)

    for country in candidates[:5]:
        log(f"Trying country: {country}")
        if myst_connect(country=country):
            new_ip = get_public_ip()
            if new_ip != old_ip and new_ip != "unknown":
                log(f"Rotation successful. IP: {old_ip} → {new_ip} (country: {country})")
                return True
            elif new_ip != "unknown":
                log(f"Connected to {country} but IP unchanged ({new_ip}). Trying next...")
                myst_disconnect()
                time.sleep(2)
            else:
                log(f"Connected to {country} but couldn't verify new IP. Assuming success.")
                return True

    log("All rotation attempts failed.")
    return False


def cmd_connect(args):
    if not check_mystvpn():
        sys.exit(1)
    country = args.country or random.choice(PREFERRED_COUNTRIES)
    if myst_connect(country=country):
        ip = get_public_ip()
        print(f"Connected to residential IP: {ip} (country: {country})")
    else:
        print("Failed to connect.", file=sys.stderr)
        sys.exit(1)


def cmd_rotate(args):
    if rotate():
        print("Rotation successful.")
    else:
        print("Rotation failed. Check logs: ~/.config/myst-rotator/rotator.log", file=sys.stderr)
        sys.exit(1)


def cmd_disconnect(args):
    if myst_disconnect():
        print("Disconnected.")
    else:
        sys.exit(1)


def cmd_status(args):
    status = myst_status()
    ip = get_public_ip()
    output = {
        "connected": status.get("connected", False),
        "country": status.get("country"),
        "public_ip": ip,
    }
    print(json.dumps(output, indent=2))


def cmd_ip(args):
    print(get_public_ip())


def cmd_countries(args):
    countries = get_countries()
    print(f"Available residential countries ({len(countries)}):")
    for c in countries:
        print(f"  {c}")


def cmd_daemon(args):
    """Auto-rotate daemon."""
    interval = args.interval or 600
    ensure_config_dir()

    # Write PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    # Signal handling for clean shutdown
    def cleanup(signum, frame):
        log("Daemon stopping (signal received).")
        if PID_FILE.exists():
            PID_FILE.unlink()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    log(f"Daemon started (interval: {interval}s, PID: {os.getpid()})")

    # Initial connect
    if not is_connected():
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
    """Check if daemon is running."""
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
    """Stop the daemon."""
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            print(f"Daemon stopped (PID: {pid}).")
            # Wait for it to die
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

    # connect
    p = sub.add_parser("connect", help="Connect to residential IP")
    p.add_argument("--country", "-c", help="Country code (e.g. US, DE, FR)")
    p.set_defaults(func=cmd_connect)

    # rotate
    p = sub.add_parser("rotate", help="Rotate to a new residential IP")
    p.set_defaults(func=cmd_rotate)

    # disconnect
    p = sub.add_parser("disconnect", help="Disconnect from VPN")
    p.set_defaults(func=cmd_disconnect)

    # status
    p = sub.add_parser("status", help="Show connection status")
    p.set_defaults(func=cmd_status)

    # ip
    p = sub.add_parser("ip", help="Show current public IP")
    p.set_defaults(func=cmd_ip)

    # countries
    p = sub.add_parser("countries", help="List available countries")
    p.set_defaults(func=cmd_countries)

    # daemon
    p = sub.add_parser("daemon", help="Run auto-rotation daemon")
    p.add_argument("--interval", "-i", type=int, default=600, help="Rotation interval in seconds (default: 600)")
    p.set_defaults(func=cmd_daemon)

    # daemon-status
    p = sub.add_parser("daemon-status", help="Check daemon status")
    p.set_defaults(func=cmd_daemon_status)

    # daemon-stop
    p = sub.add_parser("daemon-stop", help="Stop the daemon")
    p.set_defaults(func=cmd_daemon_stop)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()