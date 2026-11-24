# darktable MCP for Windows

Develop RAW photographs from any AI application that supports **local stdio MCP servers**. This repository packages two choices for Windows x64.

| Server name | Choose it for |
|---|---|
| `darktable-personal` | 23 tools for RAW development, including per-module blend modes, opacity, luminance and color masks, and editable XMP sidecars. |
| `darktable` | The official upstream 21-tool interface for module controls, styles, previews, history and export. |

The servers work with local file paths and render through a pinned Windows build of darktable. Their private catalogs let you use them alongside your usual darktable application. The AI application interprets instructions and references. Rendering runs on your PC, and the AI provider's settings govern how it handles previews.

## Install in PowerShell

1. Install **64-bit Python 3.11 or newer**. Check it with `py -3 --version`. If your Python installation provides `python` instead, substitute that command below. [Python for Windows](https://www.python.org/downloads/windows/)
2. Get the source using either method.
   - **Git:** `git clone https://github.com/utsav1232002/darktable-mcp.git`, then `cd darktable-mcp`.
   - **ZIP:** Choose **Code → Download ZIP**, extract it into a permanent folder and open PowerShell in the folder containing `setup.py`. [Download source ZIP](https://github.com/utsav1232002/darktable-mcp/archive/refs/heads/main.zip)
3. Run the setup and connection check.

```powershell
py -3 setup.py
py -3 check.py
```

Setup downloads the **246 MB** versioned runtime from GitHub Releases, verifies its SHA-256, and installs both servers into the checkout. Allow about **1.7 GB** free for both copies plus the temporary download. A preinstalled darktable, compiler and API key are unnecessary for setup. The check opens real MCP connections and reports the advertised server names and tool counts. You can rerun setup to print the configuration again.

To install only the personal server, run `py -3 setup.py --variant personal` and `py -3 check.py --variant personal`. Use `official` for the upstream server. For offline installation, download the runtime ZIP once and pass its path to setup without extracting it yourself.

```powershell
py -3 setup.py --archive 'D:\Downloads\darktable-mcp-win-x64.zip'
```

[Windows runtime and matching source archives](https://github.com/utsav1232002/darktable-mcp/releases/tag/v1.0.0)

## Connect your AI application

**Any local stdio MCP host.** Setup prints a ready-to-copy `mcpServers` JSON object with the actual Python and launcher paths on your computer. Merge the server entries into your app's MCP configuration. If it provides form fields, choose **stdio**, enter the printed `command`, and enter each member of `args` as a separate argument. Reload the host or start a fresh chat. A local model can use the same servers through an MCP-capable front end or agent. A cloud-only host needs a local connector capable of launching a Windows process.

**Codex.** Run these commands from the extracted or cloned folder after setup. Choose the line for each server you installed.

```powershell
$pythonExe = (py -3 -c "import sys; print(sys.executable)").Trim()
codex mcp add darktable-personal -- $pythonExe (Resolve-Path .\launch.py).Path codex
codex mcp add darktable -- $pythonExe (Resolve-Path .\official\launch.py).Path codex
codex mcp list
```

**Google Antigravity.** With the Antigravity CLI installed, run the following in PowerShell. Open `/mcp` in Antigravity to confirm the connection. For the settings UI or JSON configuration, `py -3 setup.py --host antigravity` prints the equivalent entries.

```powershell
$pythonExe = (py -3 -c "import sys; print(sys.executable)").Trim()
agy mcp add darktable-personal $pythonExe (Resolve-Path .\launch.py).Path antigravity
agy mcp add darktable $pythonExe (Resolve-Path .\official\launch.py).Path antigravity
```

## Make your first edit

> Use darktable-personal on a working copy of my RAW at [full path]. Increase exposure by half a stop in the highlights using a soft luminance mask at 40% opacity. Show me the preview and save the editable XMP and a full-resolution 16-bit TIFF in [output folder].

Give the assistant absolute paths that its local host can access. Importing a working copy and editing it by image ID can write an XMP beside it. Keep accompanying sidecars and mask assets when handing an edit to another host. For concurrent variants, give each session its own working copy.

**Reopen personal masks with the matching editor.** Older darktable versions, including 5.6.2, can render these newer masks differently.

```powershell
py -3 .\launch.py --open-editor 'D:\Photos\Working\example.dng'
```

## Compatibility and troubleshooting

- **Platform.** The ready-to-run package supports Windows x64. It uses darktable development build `5.7.0+2285.ga670177b18`. macOS, Linux and Windows ARM builds are outside this release.
- **Wrong tool count.** `darktable-personal` advertises 23 tools, including `blend_capabilities` and `get_blend`. `darktable` advertises 21. Check the launch path, then refresh the client.
- **Moved or renamed the folder.** Run setup again in the new location and update the absolute paths in the client.
- **Download or checksum failure.** Get the runtime ZIP for the version in `release.json` and use `--archive`. Use a fresh folder when switching releases so an existing installation stays available.
- **Large RAW timeouts.** Where supported, set the host's tool timeout to 300 seconds for full-resolution exports.
- **Private state.** Catalogs and caches live under `%LOCALAPPDATA%\darktable-personal` and `%LOCALAPPDATA%\darktable-mcp`. Set `DARKTABLE_PERSONAL_STATE_DIR` or `DARKTABLE_MCP_STATE_DIR` to use a different location.

## Source and licenses

The personal server extends the upstream native MCP. The release preserves darktable's bundled license files. The accompanying engine source archive contains the pinned darktable source and its build submodules with a revision manifest. The personal source and build scripts are in this repository. Build setup and code remain independent of the AI provider. [Personal blend controls and rebuild guide](docs/personal.md) · [Pinned upstream source](https://github.com/darktable-org/darktable/tree/a670177b18360696af9c9cb05aeb350cd8df2011) · [License](LICENSE)
