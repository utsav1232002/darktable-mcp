"""Build the personal Windows x64 frontend against the pinned darktable runtime."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

from abi import check_abi

NATIVE = Path(__file__).resolve().parent
ROOT = NATIVE.parent
CACHE = ROOT / ".build"
SDK = CACHE / "sdk" / "ucrt64"
SOURCE = CACHE / "src"
RUNTIME = ROOT / "runtime"
REVISION = "a670177b18360696af9c9cb05aeb350cd8df2011"
SOURCE_DIGEST = "9079d2efd49fc47bb74f9b5ffdb9ae6545bd754d1815a5570aef9f08824e596a"
RUNTIME_HASHES = {
    "bin/libdarktable.dll": "91369623d620a5e7f47c35dcc8b4b5c8e8899a7b537f07574d1906f2be96301a",
    "bin/darktable-mcp.exe": "370a33309f5d2693b5ba4dae4243f24b22950ad2143ca4581fb6d9db0e8a8c64",
}
LIBRARIES = (
    "libdarktable.dll", "libjson-glib-1.0-0.dll", "libglib-2.0-0.dll",
    "libgobject-2.0-0.dll", "libcairo-2.dll", "libintl-8.dll", "libsqlite3-0.dll",
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_runtime(path):
    for name, expected in RUNTIME_HASHES.items():
        if not (path / name).is_file() or sha256(path / name) != expected:
            raise ValueError(f"Expected darktable {REVISION[:10]} Windows x64 runtime at {path}. Mismatch in {name}.")


def stage_runtime(source):
    verify_runtime(source)
    if source.resolve() == RUNTIME.resolve():
        return
    if RUNTIME.exists():
        verify_runtime(RUNTIME)
        return
    # All files are separate copies. Publish only a complete tree.
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".stage-") as directory:
        pending = Path(directory) / "runtime"
        shutil.copytree(source, pending)
        verify_runtime(pending)
        pending.rename(RUNTIME)


def download(url, path, digest):
    if path.exists() and sha256(path) == digest:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temp = Path(stream.name)
    try:
        with urllib.request.urlopen(url, timeout=120) as response, temp.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if sha256(temp) != digest:
            raise ValueError(f"SHA-256 mismatch: {url}")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def prepare_sdk():
    entries = json.loads((NATIVE / "sdk-lock.json").read_bytes())
    packages = CACHE / "downloads"
    def fetch(entry):
        name = entry["file"]
        download("https://repo.msys2.org/mingw/ucrt64/" + urllib.parse.quote(name),
                 packages / name, entry["sha256"])
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(fetch, entries))
    SDK.parent.mkdir(parents=True, exist_ok=True)
    for item in entries:
        stamp = CACHE / "stamps" / item["sha256"]
        if stamp.exists() and (SDK / "bin/gcc.exe").is_file():
            continue
        subprocess.run(["tar.exe", "-xmf", str(packages / item["file"]), "-C",
                        str(SDK.parent), "ucrt64"], check=True)
        stamp.parent.mkdir(exist_ok=True)
        stamp.touch()


def prepare_source():
    archive = CACHE / "source.tar.gz"
    download("https://codeload.github.com/darktable-org/darktable/tar.gz/" + REVISION,
             archive, SOURCE_DIGEST)
    SOURCE.mkdir(exist_ok=True)
    subprocess.run(["tar.exe", "-xmf", str(archive), "-C", str(SOURCE),
                    "--strip-components", "1"], check=True)
    shutil.copyfile(NATIVE / "personal_blend.inc", SOURCE / "src/mcp/personal_blend.inc")
    # The archive sits inside our outer Git repo. Give git apply its own root.
    subprocess.run(["git", "init", "--quiet"], cwd=SOURCE, check=True)
    subprocess.run(["git", "apply", "--whitespace=nowarn",
                    str(NATIVE / "darktable-personal.patch")], cwd=SOURCE, check=True)


def write_config():
    # The frontend consumes the same inline headers and struct layouts as libdarktable.
    # Generate its small private config.h from the pinned upstream template.
    values = {
        "CMAKE_PROJECT_NAME": "darktable",
        "REL_BIN_TO_LOCALEDIR": "../share/locale", "REL_BIN_TO_LIBDIR": "../lib/darktable",
        "REL_BIN_TO_DATADIR": "../share/darktable", "REL_BIN_TO_SHAREDIR": "../share",
        "CMAKE_SHARED_MODULE_PREFIX": "lib", "CMAKE_SHARED_MODULE_SUFFIX": ".dll",
        "WANTED_STACK_SIZE": "2097152", "WANTED_THREADS_STACK_SIZE": "2097152",
        "DT_SUPPORTED_EXTENSIONS_STRING": "", "IsoCodes_LOCATION": "../share/iso-codes",
        "IsoCodes_LOCALEDIR": "../share/locale",
    }
    enabled = {"DARKTABLE_LOCALEDIR", "DARKTABLE_LIBDIR", "DARKTABLE_DATADIR",
               "DARKTABLE_SHAREDIR", "HAVE_CPUID_H", "HAVE___GET_CPUID",
               "HAVE_OMP_FIRSTPRIVATE_WITH_CONST"}
    template = (SOURCE / "src/config.cmake.h").read_text(encoding="utf-8")
    template = re.sub(r"^#cmakedefine (\w+)(.*)$",
                      lambda m: f"#define {m[1]}{m[2]}" if m[1] in enabled else "",
                      template, flags=re.MULTILINE)
    template = re.sub(r"@(\w+)@", lambda m: values[m[1]], template)
    (CACHE / "config.h").write_text(template, encoding="utf-8")


def compile_frontend(output):
    write_config()
    env = os.environ.copy()
    env["PATH"] = str(SDK / "bin") + os.pathsep + env["PATH"]
    include = SDK / "include"
    include_dirs = [CACHE, SOURCE / "src", SOURCE / "src/external/LuaAutoC",
                    SDK / "lib/glib-2.0/include"]
    include_dirs.extend(include / name for name in (
        "glib-2.0", "json-glib-1.0", "gtk-3.0", "atk-1.0", "pango-1.0", "harfbuzz",
        "gdk-pixbuf-2.0", "cairo", "freetype2", "lua5.4", "libpng16",
        "librsvg-2.0", "osmgpsmap-1.0"))
    defines = ("NDEBUG", "HAVE_CONFIG_H", "HAVE_OPENCL", "HAVE_AI", "USE_LUA",
               "HAVE_GPHOTO2", "HAVE_MAP", "HAVE_PRINT", "HAVE_WINDOWS_CREDENTIALS")
    command = [str(SDK / "bin/gcc.exe"), "-std=gnu99", "-O2", "-g", "-fopenmp",
               "-mthreads", "-municode", *("-D" + name for name in defines),
               *("-I" + str(path) for path in include_dirs)]
    command.extend(str(SOURCE / "src/mcp" / name)
                   for name in ("main.c", "mcp_jsonrpc.c", "mcp_tools.c", "dt_bridge.c"))
    command.extend(str(RUNTIME / "bin" / name) for name in LIBRARIES)
    subprocess.run(command + ["-Wl,--no-insert-timestamp", "-o", str(output)],
                   env=env, cwd=SOURCE, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-source", type=Path, default=ROOT / "official/runtime",
                        help="Previously verified, extracted official Windows x64 nightly runtime")
    args = parser.parse_args()
    if os.name != "nt" or sys.version_info < (3, 11):
        parser.error("Windows x64 and Python 3.11 or later are required")
    CACHE.mkdir(exist_ok=True)
    stage_runtime(args.runtime_source.resolve() if args.runtime_source.is_dir() else RUNTIME)
    prepare_sdk()
    prepare_source()
    with tempfile.TemporaryDirectory(dir=CACHE) as temp:
        exe = Path(temp) / "darktable-personal.exe"
        compile_frontend(exe)
        check_abi(RUNTIME / "bin/.debug/darktable-mcp.exe.dbg", exe, SDK / "bin/objdump.exe")
        manifest = Path(temp) / "mcp_tools.json"
        shutil.copy2(SOURCE / "data/mcp_tools.json", manifest)
        if "get_blend" not in {tool["name"] for tool in json.loads(manifest.read_bytes())}:
            raise RuntimeError("The staged server manifest lacks the personal blending tools")
        exe.replace(RUNTIME / "bin/darktable-personal.exe")
        manifest.replace(RUNTIME / "share/darktable/mcp_tools.json")
    print("Built " + str(RUNTIME / "bin/darktable-personal.exe"))


if __name__ == "__main__":
    main()
