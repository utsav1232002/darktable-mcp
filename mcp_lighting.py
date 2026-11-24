"""Expose the same portrait lighting guidance through both native MCP launchers."""

import json
import os
import subprocess
import sys
from threading import Thread


LIGHTING_GUIDANCE = """Preserve captured lighting in reference-guided RAW edits.

Use the source to decide where the light belongs and the reference to guide the look. Preserve the direction, softness, falloff, and relationships between lit and shaded surfaces unless the user explicitly requests relighting. Work from a reversible preview.

1. Inspect a neutral baseline. Trace the existing light across the face, neck, shoulders, arms, and hands, including fingers against hair. Use gradients, cast shadows, and catchlights together. Preserve ambiguous transitions.
2. Translate the reference into compatible qualities such as luminous skin, deep blacks with readable texture, highlight roll-off, or subject separation. Set the global exposure, color or monochrome mix, and tone curve first. Compare lit and shaded areas of the same material and the transition between them. Use linear luminance for any rendered ratio. A processed reference cannot establish the capture lighting ratio.
3. For each dodge or burn, name the existing cue it strengthens and the neighboring surfaces it must protect. Start with the smallest useful change. Follow the existing light across the form. Inspect the mask where a background burn crosses fingers, hair, clothing, or skin.
4. Before committing or delivering, compare the global grade, the finished grade, and the finished grade with each local adjustment toggled off. Inspect at fit view and at 100% around each boundary, including both sides of the mask. Use the overlay to find spill and hide it to judge the photograph. Inspect the combined stack for reinforcing mask edges.
5. Revise or remove any adjustment that introduces a halo, band, isolated bright patch, spill onto a neighboring surface, or abrupt falloff unsupported by a contour or cast shadow. If visual review is unavailable or the correction still fails, deliver the verified global grade or describe the unverified preview as a draft. A histogram and a successful render cannot verify lighting continuity."""


def _add_guidance(line):
    try:
        reply = json.loads(line)
    except (ValueError, UnicodeDecodeError):
        return line
    result = reply.get("result") if isinstance(reply, dict) else None
    if not isinstance(result, dict):
        return line
    if "serverInfo" in result and "protocolVersion" in result:
        previous = result.get("instructions")
        result["instructions"] = "\n\n".join(filter(None, (previous, LIGHTING_GUIDANCE)))
    elif isinstance(result.get("tools"), list):
        for tool in result["tools"]:
            if tool.get("name") in ("render", "export_images"):
                tool["description"] = tool.get("description", "") + "\n\n" + LIGHTING_GUIDANCE
    else:
        return line
    return json.dumps(reply).encode("utf-8") + b"\n"


def _forward_requests(destination):
    try:
        with destination:
            # Read without locking Python stdin while an idle client waits for replies.
            while chunk := os.read(sys.stdin.fileno(), 65536):
                destination.write(chunk)
                destination.flush()
    except BrokenPipeError:
        pass


def run_mcp(args, **kwargs):
    """Forward native requests and add workflow guidance to discovery responses."""
    with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, **kwargs) as engine:
        Thread(target=_forward_requests, args=(engine.stdin,), daemon=True).start()
        try:
            for line in engine.stdout:
                sys.stdout.buffer.write(_add_guidance(line))
                sys.stdout.buffer.flush()
        except BrokenPipeError:
            engine.terminate()
        except BaseException:
            engine.terminate()
            raise
        return engine.wait()
