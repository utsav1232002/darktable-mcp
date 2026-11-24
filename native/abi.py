"""Check darktable structure sizes and member offsets using the official frontend DWARF."""
from pathlib import Path
import re
import subprocess


ENTRY = re.compile(r"^\s*<(\d+)><[0-9a-fA-F]+>: Abbrev Number: \d+(?: \(DW_TAG_(\w+)\))?")
ATTRIBUTE = re.compile(r"\bDW_AT_(name|byte_size|data_member_location|data_bit_offset|bit_size)\s+: (.+)$")


def layouts(executable, objdump):
    text = subprocess.check_output([str(objdump), "--dwarf=info", str(executable)])
    tree = {}
    stack = []

    def finish(node):
        kind, attrs, members = node
        if kind == "member" and stack and stack[-1][0] in ("structure_type", "union_type"):
            members = stack[-1][2]
            members.append(tuple(attrs.get(k) for k in ("name", "data_member_location", "data_bit_offset", "bit_size")))
        if kind in ("structure_type", "union_type") and "byte_size" in attrs:
            name = attrs.get("name", "")
            if name.startswith("dt_") or name == "darktable_t":
                definition = (attrs["byte_size"], tuple(members))
                if name in tree and tree[name] != definition:
                    raise ValueError(f"Inconsistent {name} across compilation units in {executable}")
                tree[name] = definition

    for line in text.decode("utf-8", errors="replace").splitlines():
        entry = ENTRY.match(line)
        if entry:
            depth, kind = int(entry[1]), entry[2]
            while len(stack) > depth:
                finish(stack.pop())
            if kind:
                stack.append((kind, {}, []))
            continue
        attr = ATTRIBUTE.search(line)
        if attr and stack:
            value = re.sub(r"^\(indirect [^)]*\): ", "", attr[2])
            stack[-1][1][attr[1]] = value
    while stack:
        finish(stack.pop())
    return tree


def check_abi(reference, candidate, objdump):
    expected = layouts(Path(reference), objdump)
    actual = layouts(Path(candidate), objdump)
    required = {"dt_develop_blend_params_t", "dt_iop_module_t", "dt_develop_t", "dt_image_t"}
    if not required.issubset(expected) or not required.issubset(actual):
        raise RuntimeError("Missing debug definitions needed to verify the runtime ABI")
    missing = expected.keys() - actual.keys()
    mismatches = sorted(name for name in expected.keys() & actual.keys() if expected[name] != actual[name])
    if mismatches or missing:
        raise RuntimeError("Incompatible darktable layouts: " + ", ".join(sorted(set(mismatches) | missing)))
    print(f"Verified {len(expected)} official darktable structure sizes and member layouts")
