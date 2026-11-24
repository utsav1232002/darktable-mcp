"""Install either local stdio MCP on Windows x64 using the pinned release archive."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
LOCK = json.loads((ROOT / "release.json").read_text(encoding="utf-8"))
BASE = "https://github.com/utsav1232002/darktable-mcp/releases/download/"
HOSTS = {"official": ("darktable", ROOT / "official"), "personal": ("darktable-personal", ROOT)}


def digest(file):
    with file.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(directory, variant):
    name = "darktable-mcp" if variant == "official" else "darktable-personal"
    checks = [(directory / "bin" / (name + ".exe"), LOCK[variant]),
              (directory / "share/darktable/mcp_tools.json", LOCK[variant + "_schema"])]
    if any(not file.is_file() or digest(file) != expected for file, expected in checks):
        raise ValueError(f"Unexpected installation at {directory}. Set up this release in a fresh folder.")


def install_variant(archive, variant):
    target = HOSTS[variant][1] / "runtime"
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".setup-") as stage:
        engine = Path(stage) / "engine"
        archive.extractall(stage, [i for i in archive.namelist() if i.startswith("engine/")])
        if variant == "personal":
            for file in ["bin/darktable-personal.exe", "share/darktable/mcp_tools.json"]:
                with archive.open("personal/" + file) as src, (engine / file).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
        verify(engine, variant)
        engine.rename(target)
    print(f"Installed {variant} at {target}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--variant", choices=["both", *HOSTS], default="both")
    parser.add_argument("--archive", type=Path, help="use a downloaded release runtime ZIP")
    parser.add_argument("--host", choices=["local", "codex", "antigravity"], default="local",
                        help="select the private catalog profile in the printed client configuration")
    args = parser.parse_args()
    if os.name != "nt" or sys.version_info < (3, 11) or platform.machine().lower() not in {"amd64","x86_64"}:
        parser.error("Use 64-bit Python 3.11 or newer on Windows x64.")
    variants = list(HOSTS) if args.variant == "both" else [args.variant]
    pending = []
    for variant in variants:
        directory = HOSTS[variant][1] / "runtime"
        if directory.exists():
            verify(directory, variant)
        else:
            pending.append(variant)
    if pending:
        with tempfile.TemporaryDirectory(prefix="darktable-download-") as temp:
            archive = args.archive
            if not archive:
                archive = Path(temp) / LOCK["archive"]
                url = BASE + LOCK["release"] + "/" + LOCK["archive"]
                print(f"Downloading {url}", file=sys.stderr)
                with urllib.request.urlopen(url, timeout=120) as src, archive.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
            if digest(archive) != LOCK["sha256"]:
                raise ValueError("Archive checksum mismatch. Download the runtime ZIP for this source version.")
            with zipfile.ZipFile(archive) as contents:
                for variant in pending:
                    install_variant(contents, variant)
    servers = {HOSTS[v][0]: {"command": sys.executable,
                             "args": [str(HOSTS[v][1] / "launch.py"), args.host]} for v in variants}
    print(json.dumps({"mcpServers": servers}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, zipfile.BadZipFile, KeyError) as exc:
        sys.exit(f"Setup failed: {exc}")
