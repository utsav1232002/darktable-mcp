"""A tiny, deterministic Bayer DNG with grey, red, green and blue exposure ramps."""

from pathlib import Path
import struct

import numpy as np


PATCH = 48
LEVELS = (0.012, 0.025, 0.05, 0.10, 0.20, 0.32, 0.48, 0.65)
PATCHES = ((1, 1, 1), (1, .07, .04), (.04, 1, .07), (.04, .07, 1))


def write_chart(path: Path) -> None:
    height, width = len(PATCHES) * PATCH, len(LEVELS) * PATCH
    y, x = np.indices((height, width))
    bayer_channel = np.where(y % 2 == x % 2, np.where(y % 2 == 0, 0, 2), 1)
    level = np.array(LEVELS)[x // PATCH] * np.array(PATCHES)[y // PATCH, bayer_channel]
    pixels = np.round(64 + level * (16383 - 64)).astype("<u2").tobytes()

    # An uncompressed, single-strip DNG. Values in the DNG tags follow the
    # sample's black and white levels; the matrix approximates an sRGB sensor.
    tags = {}
    def numbers(tag, kind, items):
        fmt = {1: "B", 3: "H", 4: "I"}[kind]
        tags[tag] = (kind, len(items), struct.pack("<" + fmt * len(items), *items))

    def string(tag, value):
        body = value.encode("ascii") + bytes(1)
        tags[tag] = (2, len(body), body)

    def rationals(tag, pairs, signed=False):
        fmt = "<ii" if signed else "<II"
        tags[tag] = (10 if signed else 5, len(pairs), b"".join(struct.pack(fmt, *p) for p in pairs))

    for tag, value in {254: 0, 256: width, 257: height, 273: 0, 278: height,
                       279: len(pixels), 50717: 16383}.items():
        numbers(tag, 4, [value])
    for tag, value in {258: 16, 259: 1, 262: 32803, 274: 1, 277: 1, 284: 1,
                       50711: 1, 50714: 64, 50778: 21}.items():
        numbers(tag, 3, [value])
    numbers(33421, 3, [2, 2])
    numbers(33422, 1, [0, 1, 1, 2])
    numbers(50706, 1, [1, 4, 0, 0])
    numbers(50707, 1, [1, 1, 0, 0])
    numbers(50710, 1, [0, 1, 2])
    numbers(50713, 3, [1, 1])
    numbers(50829, 4, [0, 0, height, width])
    string(271, "Test Fixture")
    string(272, "Synthetic CFA")
    string(50708, "Synthetic darktable blend chart")
    matrix = (32405, -15371, -4985, -9693, 18760, 415, 556, -2040, 10572)
    rationals(50721, [(v, 10000) for v in matrix], signed=True)
    rationals(50728, [(1, 1)] * 3)

    offset = 8 + 2 + 12 * len(tags) + 4
    extra = bytearray()
    entries = []
    for tag, (kind, count, raw) in sorted(tags.items()):
        if len(raw) > 4:
            entry = struct.pack("<I", offset + len(extra))
            extra.extend(raw)
            if len(extra) % 2:
                extra.append(0)
        else:
            entry = raw.ljust(4, bytes(1))
        entries.append((tag, kind, count, entry))
    result = bytearray(b"II" + struct.pack("<HIH", 42, 8, len(tags)))
    for tag, kind, count, entry in entries:
        if tag == 273:
            entry = struct.pack("<I", offset + len(extra))
        result.extend(struct.pack("<HHI", tag, kind, count) + entry)
    path.write_bytes(result + bytes(4) + extra + pixels)
