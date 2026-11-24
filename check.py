"""Check the local MCP protocol handshake and advertised tools without using an AI model."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def check(name, launcher, expected):
    requests = [
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
         "clientInfo": {"name": "installation-check", "version": "1"}, "capabilities": {}}},
        {"method": "notifications/initialized"},
        {"id": 2, "method": "tools/list", "params": {}},
    ]
    payload = "".join(json.dumps({"jsonrpc": "2.0", **message}) + "\n" for message in requests)
    result = subprocess.run([sys.executable, str(launcher), "local"], input=payload,
                            text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f"{name} failed to start: {result.stderr.strip()}")
    replies = {row.get("id"): row for row in map(json.loads, result.stdout.splitlines())}
    identity = replies[1]["result"]["serverInfo"]["name"]
    tools = replies[2]["result"]["tools"]
    if identity != name or len(tools) != expected:
        raise RuntimeError(f"{name} returned identity {identity} and {len(tools)} tools")
    print(f"{identity}: connected, {len(tools)} tools")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["both", "official", "personal"], default="both")
    variant = parser.parse_args().variant
    try:
        if variant != "personal":
            check("darktable-mcp", ROOT / "official/launch.py", 21)
        if variant != "official":
            check("darktable-personal", ROOT / "launch.py", 23)
    except (OSError, RuntimeError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        sys.exit(f"Connection check failed: {exc}")
