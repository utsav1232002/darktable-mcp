"""Launch the personal Windows MCP, or open an edited RAW in its matching darktable GUI."""

import argparse
import itertools
import msvcrt
import os
from pathlib import Path
import subprocess
import sys

from mcp_lighting import run_mcp


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
    parser.add_argument("--open-editor", type=Path, metavar="RAW", help="open a working RAW and its adjacent XMP in the matching GUI")
    options = parser.parse_args()
    photo = options.open_editor
    if photo and not photo.is_file():
        parser.error(f"Cannot find working image {photo}")
    host = "editor" if photo else options.host
    binary = "darktable.exe" if photo else "darktable-personal.exe"
    executable = Path(__file__).resolve().parent / "runtime" / "bin" / binary
    if not executable.is_file():
        parser.exit(1, f"Missing darktable MCP executable at {executable}\n")

    state_root = os.environ.get("DARKTABLE_PERSONAL_STATE_DIR") or Path(os.environ["LOCALAPPDATA"]) / "darktable-personal"
    profile, fd = reserve_catalog(Path(state_root).resolve() / host)
    try:
        config, cache, scratch = (profile / name for name in ("config", "cache", "tmp"))
        for directory in (config, cache, scratch):
            directory.mkdir(exist_ok=True)
        # Keep the reservation alive if the client terminates the launcher before darktable.
        handle = msvcrt.get_osfhandle(fd)
        os.set_handle_inheritable(handle, True)
        startup = subprocess.STARTUPINFO(lpAttributeList={"handle_list": [handle]})
        initial = [photo.resolve().as_posix(), "--library", ":memory:"] if photo else ["--core"]
        # The MCP temporarily mutes sidecars during scratch renders. A --conf
        # override would mask that temporary change. Use its native on-import default.
        sidecar_args = ["--conf", "write_sidecar_files=after edit"] if photo else []
        args = [
            str(executable), *initial, "--configdir", config.as_posix(), "--cachedir", cache.as_posix(),
            "--tmpdir", scratch.as_posix(), *sidecar_args,
            "--conf", "plugins/imageio/format/tiff/bpp=16",
        ]
        process_options = {
            "cwd": executable.parent,
            "startupinfo": startup,
            "creationflags": subprocess.CREATE_NO_WINDOW,
        }
        if photo:
            return subprocess.run(args, **process_options).returncode
        return run_mcp(args, **process_options)
    finally:
        os.close(fd)


if __name__ == "__main__":
    sys.exit(main())
