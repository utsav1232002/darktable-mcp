"""Run the upstream Windows darktable MCP binary with an available private catalog."""

import argparse
import itertools
import msvcrt
import os
from pathlib import Path
import subprocess
import sys


def reserve_catalog(host_dir):
    # darktable locks both library.db and data.db. Simultaneous chats each need a profile.
    for index in itertools.count(1):
        profile = host_dir / f"profile-{index}"
        profile.mkdir(parents=True, exist_ok=True)
        marker = profile / ".in-use"
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_TEMPORARY)
        except FileExistsError:
            continue
        except PermissionError:
            if marker.exists():
                continue
            raise
        return profile, fd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", nargs="?", choices=("local", "codex", "antigravity"), default="local")
    host = parser.parse_args().host
    executable = Path(__file__).resolve().parent / "runtime" / "bin" / "darktable-mcp.exe"
    if not executable.is_file():
        parser.exit(1, f"Missing darktable MCP executable at {executable}\n")

    state_root = os.environ.get("DARKTABLE_MCP_STATE_DIR") or Path(os.environ["LOCALAPPDATA"]) / "darktable-mcp"
    profile, fd = reserve_catalog(Path(state_root).resolve() / host)
    try:
        config, cache, scratch = (profile / name for name in ("config", "cache", "tmp"))
        for directory in (config, cache, scratch):
            directory.mkdir(exist_ok=True)
        # Keep the reservation alive if the client terminates the launcher before darktable.
        handle = msvcrt.get_osfhandle(fd)
        os.set_handle_inheritable(handle, True)
        startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [handle]})
        args = [
            str(executable), "--core", "--configdir", config.as_posix(), "--cachedir", cache.as_posix(),
            "--tmpdir", scratch.as_posix(),
            "--conf", "plugins/imageio/format/tiff/bpp=16",
        ]
        return subprocess.run(
            args, cwd=executable.parent, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr,
            startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
        ).returncode
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
