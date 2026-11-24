# Personal darktable MCP

A local Windows x64 MCP server for developing RAW photographs with editable darktable module settings, blend modes and parametric masks. The native extension targets darktable commit `a670177b18360696af9c9cb05aeb350cd8df2011`. Codex and Google Antigravity can launch the personal server over stdio under the name `darktable-personal`.

## Using a mask

> Use **darktable-personal** on a working copy of this RAW. Add an exposure instance for the highlights. Select the highlights with a luminance mask, give the transition a soft edge, and set the module opacity to 40%. Show me the preview and save the editable XMP.

The assistant should import a working copy and its existing sidecars, inspect the available blend controls, apply settings to the desired module instance, and inspect the rendered result and saved settings. A scratch preview of a loose file lasts for one request. Editing an imported image by its catalog image ID commits the edit. Export using the returned image ID and an explicit output path. TIFFs default to 16 bits per channel.

The personal server exposes 23 tools. `blend_capabilities` accepts an optional operation name and reports the module's blend support, color spaces and channel choices. The installed engine reports 70 blend-capable modules among 97 processing modules. Of those, 67 support parametric masks. `get_blend` reads a saved module instance using its image ID, operation and optional `multi_priority`.

Pass a `blend` object in a `render` or `image_stats` stack entry. The following example adds one stop of exposure at 40% opacity to a luminance range. The four thresholds set the start and end of the rising and falling transitions in normalized darktable slider coordinates.

```json
{
  "operation": "exposure",
  "multi_priority": 1,
  "params": {"exposure": 1.0},
  "blend": {
    "colorspace": "display_rgb",
    "mode": "normal",
    "opacity": 40,
    "mask": {
      "type": "parametric",
      "channels": {"luminance": {"thresholds": [0.4, 0.6, 1.0, 1.0]}}
    }
  }
}
```

Target an existing instance by priority or use the next consecutive priority to create one on a multi-instance module. Omit `mask` to keep its selection while adjusting opacity, blend mode, blend direction, or refinement. Supplying `mask` replaces that instance's mask. Use `{"type":"uniform"}` for uniform application. The mask interface supports input and output channels, per-channel and whole-mask inversion, and union or intersection. Display RGB provides HSL hue and saturation. Scene RGB provides hue and chroma. Available refinements include feather radius and guide, blur radius, contrast, brightness and details. The `fulcrum_ev` control applies to supported scene-RGB blend modes. Hand-drawn brush and path creation are outside this interface.

## Reopening the edit

Use the matching bundled darktable editor to review or refine new masks. The personal runtime writes a newer blend format than the separately installed darktable 5.6.2. A local comparison showed that 5.6.2 discarded the effect of a newer opacity setting. The matching editor opens the supplied working RAW with its adjacent sidecars in a private profile and a fresh in-memory photo catalog.

```powershell
py -3 .\launch.py --open-editor 'D:\Photos\Working\example.dng'
```

The upstream engine and derived code use the GNU GPL. [Source at the pinned revision](https://github.com/darktable-org/darktable/tree/a670177b18360696af9c9cb05aeb350cd8df2011) Â· [License](../LICENSE)

## Rebuilding from this repository

On Windows x64, install Python 3.11 or newer and Git, and make the matching extracted darktable runtime available. From the repository root run the following command, substituting its location if needed.

```powershell
py -3 native/build.py --runtime-source .\official\runtime
```

The build stages a private runtime, downloads the pinned darktable source and compiler dependencies, and compiles the personal executable. Build downloads use GitHub and MSYS2. The Git repository contains the personal source changes, build instructions and tests. The generated runtime and toolchain are stored locally outside Git history.

The native blend implementation is in [personal_blend.inc](../native/personal_blend.inc). The remaining integration changes are in the [upstream patch](../native/darktable-personal.patch). The build checks 103 native structure layouts against the official Windows debug information. For the RAW integration test, install the Python test packages `mcp`, `Pillow` and `numpy`, then run `python -m unittest discover -s tests -v`.

On 24 November 2026, Codex discovered 23 tools and the Antigravity MCP manager showed the personal server connected. A synthetic color RAW verified the effects of luminance, hue and saturation masks, inversion, combined masks, opacity, blend mode and fulcrum. Separate exposure instances retained different masks. A fresh import reproduced the preview pixels exactly. The matching darktable CLI also reproduced the 16-bit masked export in a comparison of its RGB values converted to 8 bits. Darktable 5.6.2 rendered the same sidecar differently.
