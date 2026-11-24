"""Run with python -m unittest discover -s tests. Requires mcp, Pillow and NumPy."""

import asyncio
import base64
from contextlib import asynccontextmanager
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import numpy as np
from PIL import Image

from raw_chart import LEVELS, PATCH, PATCHES, write_chart


LAUNCHER = Path(__file__).resolve().parents[1] / "launch.py"
DT = "{http://darktable.sf.net/}"


@asynccontextmanager
async def server(work: Path):
    work.mkdir(exist_ok=True)
    params = StdioServerParameters(command=sys.executable, args=[str(LAUNCHER), "local"],
        env={**os.environ, "DARKTABLE_PERSONAL_STATE_DIR": str(work / "state")})
    with (work / "server.log").open("w", encoding="utf-8") as log:
        async with stdio_client(params, errlog=log) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def response_text(result):
    return " ".join(block.text for block in result.content if block.type == "text")


async def call(session, name, args):
    result = await session.call_tool(name, args)
    if result.isError:
        raise AssertionError(f"{name} failed: {response_text(result)}")
    return result


async def saved_blend(session, image_id, instance=0):
    result = await call(session, "get_blend", {
        "imgid": image_id, "operation": "exposure", "multi_priority": instance})
    return json.loads(response_text(result))["blend"]


def layer(blend):
    return {"operation": "exposure", "enabled": True, "params": {"exposure": 1.55}, "blend": blend}


def mask(**thresholds):
    return {"type": "parametric", "combine": "intersection",
            "channels": {name: {"thresholds": values} for name, values in thresholds.items()}}


async def preview(session, source, blend=None):
    args = {"input": source, "width": len(LEVELS) * PATCH}
    if blend is not None:
        args["stack"] = [layer(blend)]
    result = await call(session, "render", args)
    block, = (b for b in result.content if b.type == "image")
    with Image.open(BytesIO(base64.b64decode(block.data))) as image:
        if image.size != (len(LEVELS) * PATCH, len(PATCHES) * PATCH):
            raise AssertionError(f"Unexpected preview size {image.size}")
        return np.array(image.convert("RGB"))


def patch_delta(before, after):
    delta = np.abs(after.astype(np.float32) - before.astype(np.float32))
    return np.array([[np.mean(delta[row * PATCH + 14:(row + 1) * PATCH - 14,
                                   col * PATCH + 14:(col + 1) * PATCH - 14])
                      for col in range(len(LEVELS))] for row in range(len(PATCHES))])


async def import_chart(session, file):
    result = await call(session, "import_images", {"paths": [file.as_posix()]})
    return json.loads(response_text(result))["images"][0]["imgid"]


class NativeBlend(unittest.TestCase):
    def test_render_and_xmp(self):
        # Set this for interoperability checks against a second darktable build.
        keep = os.environ.get("DARKTABLE_PERSONAL_QA_OUTPUT")
        if keep:
            temp = Path(tempfile.mkdtemp(prefix="darktable-personal-qa-", dir=keep))
            print(f"Retained native blend fixtures: {temp}", flush=True)
            asyncio.run(self.run_chart(temp))
            return
        with tempfile.TemporaryDirectory(prefix="darktable-personal-qa-") as temp:
            asyncio.run(self.run_chart(Path(temp)))

    async def run_chart(self, temp):
        raw = temp / "chart.dng"
        write_chart(raw)
        original = sha256(raw.read_bytes()).digest()
        scratch = {"path": raw.as_posix()}
        normal = {"mode": "normal", "colorspace": "display_rgb", "opacity": 100}
        luminance = mask(luminance=[.13, .17, 1, 1])
        green = mask(hue=[.18, .25, .41, .47])
        saturated = mask(saturation=[.13, .23, 1, 1])

        async with server(temp / "author") as session:
            caps = await call(session, "blend_capabilities", {})
            self.assertIn("saturation", response_text(caps))
            zero = await preview(session, scratch, {**normal, "opacity": 0})
            half = await preview(session, scratch, {**normal, "opacity": 50})
            full = await preview(session, scratch, normal)
            Image.fromarray(full).save(temp / "full-strength.png")
            full_delta = patch_delta(zero, full)
            half_delta = patch_delta(zero, half)
            self.assertGreater(full_delta.mean(), 8)
            self.assertGreater(half_delta.mean(), full_delta.mean() * .2)
            self.assertLess(half_delta.mean(), full_delta.mean() * .85)
            multiplied = await preview(session, scratch, {**normal, "mode": "multiply"})
            self.assertGreater(patch_delta(full, multiplied).mean(), 5)
            scene = {"colorspace": "scene_rgb", "mode": "multiply", "opacity": 100}
            first = await preview(session, scratch, {**scene, "fulcrum_ev": 0})
            shifted = await preview(session, scratch, {**scene, "fulcrum_ev": 2})
            self.assertGreater(patch_delta(first, shifted).mean(), 1)
            mid_gray = (PATCH // 2, PATCH * 3 + PATCH // 2)
            self.assertLess(multiplied[mid_gray].mean() + 4, zero[mid_gray].mean())

            async def response(selection):
                image = await preview(session, scratch, {**normal, "mask": selection})
                return patch_delta(zero, image) / np.maximum(full_delta, 1)

            light, hue, sat = [await response(m) for m in (luminance, green, saturated)]
            # Row zero is neutral. Rows one to three are red, green, and blue.
            # Sample patch interiors to avoid demosaicing and resampling boundaries.
            self.assertLess(light[0, 0], .12, light)
            self.assertGreater(light[0, -1], .85, light)
            self.assertGreater(hue[2, 4], .85, hue)
            self.assertLess(max(hue[1, 4], hue[3, 4]), .12, hue)
            self.assertLess(sat[0, 4], .12, sat)
            self.assertGreater(min(sat[1:, 4]), .85, sat)
            inverted = await response({**green, "invert": True})
            self.assertLess(inverted[2, 4], .12, inverted)
            self.assertGreater(min(inverted[1, 4], inverted[3, 4]), .85, inverted)
            combined = mask(hue=green["channels"]["hue"]["thresholds"],
                            luminance=luminance["channels"]["luminance"]["thresholds"])
            intersection = await response(combined)
            union = await response({**combined, "combine": "union"})
            self.assertLess(intersection[1, -1], .12, intersection)
            self.assertGreater(union[1, -1], .85, union)
            self.assertLess(intersection[2, 0], .12, intersection)
            self.assertGreater(union[2, 0], .85, union)

            # Import only after scratch renders. Apply an editable half-strength
            # color selection; record the state before submitting invalid edits.
            self.assertFalse(raw.with_suffix(".dng.xmp").exists())
            image_id = await import_chart(session, raw)
            source = {"imgid": image_id}
            requested = {**normal, "opacity": 62, "mask": green,
                         "refinement": {"blur_radius": 2.0}}
            committed = await preview(session, source, requested)
            saved = await saved_blend(session, image_id)
            self.assertEqual(saved["mode"], "normal")
            self.assertAlmostEqual(saved["opacity"], 62)
            self.assertAlmostEqual(saved["refinement"]["blur_radius"], 2.0)
            self.assertEqual(saved["mask"]["type"], "parametric")
            actual = saved["mask"]["channels"]["hue"]["thresholds"]
            np.testing.assert_allclose(actual, green["channels"]["hue"]["thresholds"], atol=1e-6)
            for opacity in (28, 62):
                await call(session, "render", {"input": source, "width": 96,
                    "stack": [{"operation": "exposure", "blend": {"opacity": opacity}}]})
                current = await saved_blend(session, image_id)
                self.assertEqual(current["mask"], saved["mask"])
                self.assertEqual(current["opacity"], opacity)
            for bad in ({"mode": "unknown-test-mode"}, {"opacity": 150},
                        {"mask": mask(hue=[0, .8, .4, 1])}, {"mask": {"type": "drawn"}},
                        {"colorspace": "scene_rgb", "mask": saturated}):
                result = await session.call_tool("render", {"input": source, "stack": [layer(bad)]})
                self.assertTrue(result.isError, bad)
                self.assertTrue(response_text(result).strip())
            self.assertEqual(await saved_blend(session, image_id), saved)
            np.testing.assert_array_equal(await preview(session, source), committed)

            second = layer({**normal, "opacity": 35, "mask": {**luminance, "invert": True}})
            second["multi_priority"] = 1
            await call(session, "render", {"input": source, "width": 96, "stack": [second]})
            self.assertEqual(await saved_blend(session, image_id), saved)
            saved_second = await saved_blend(session, image_id, 1)
            self.assertTrue(saved_second["mask"]["invert"])
            self.assertEqual(saved_second["opacity"], 35)
            final = await preview(session, source)
            self.assertGreater(patch_delta(committed, final).max(), 3)
            Image.fromarray(final).save(temp / "masked.png")

        sidecar = raw.with_suffix(".dng.xmp")
        self.assertTrue(any(n.get(DT + "operation") == "exposure" and n.get(DT + "blendop_params")
                            for n in ET.parse(sidecar).iter()))
        # Start with a different database and source path: only the XMP can
        # carry the native blend state across this boundary.
        clone = temp / "clone.dng"
        shutil.copyfile(raw, clone)
        shutil.copyfile(sidecar, clone.with_suffix(".dng.xmp"))
        async with server(temp / "reader") as session:
            image_id = await import_chart(session, clone)
            self.assertEqual(await saved_blend(session, image_id), saved)
            self.assertEqual(await saved_blend(session, image_id, 1), saved_second)
            np.testing.assert_array_equal(await preview(session, {"imgid": image_id}), final)
        self.assertEqual(sha256(raw.read_bytes()).digest(), original)


if __name__ == "__main__":
    unittest.main()
