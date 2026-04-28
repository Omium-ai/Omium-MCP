# Omium — Quickstart

Get from `pip install` to a working integration in under 5 minutes.

`pip install omium` ships the **Omium MCP server** (`omium-mcp`) bundled with the SDK. This guide walks you through installing the package and pointing an AI client (Claude Code, Claude Desktop, Cursor) at it so the assistant can read your Omium account in plain English.

(For SDK usage in your own Python code — checkpoints, tracing, LangChain/LangGraph/CrewAI integration — see the SDK docs separately.)

---

## Prerequisites

- Python **3.10 or newer** (`python3 --version` on macOS/Linux, `python --version` on Windows)
- An Omium API key — copy it from your Omium dashboard

> **Shell note:** This guide shows commands for **bash/zsh** (macOS, Linux, WSL, Git Bash) and **Windows PowerShell**. Pick the block that matches your terminal. Windows native `cmd.exe` users should switch to PowerShell — most commands won't translate cleanly to cmd.

---

## Install

**macOS / Linux:**

```bash
python3 -m venv ~/omium
~/omium/bin/pip install --upgrade pip
~/omium/bin/pip install omium
```

**Windows (PowerShell):**

```powershell
python -m venv $HOME\omium
& "$HOME\omium\Scripts\pip" install --upgrade pip
& "$HOME\omium\Scripts\pip" install omium
```

> The Windows venv stores its scripts under `Scripts\`, not `bin/` — that's the only structural difference.

Confirm both packages landed:

**macOS / Linux:**

```bash
~/omium/bin/pip list | grep -iE "^omium|^mcp"
```

**Windows (PowerShell):**

```powershell
& "$HOME\omium\Scripts\pip" list | Select-String -Pattern '^omium','^mcp '
```

Expected output (either OS):

```
mcp        1.27.0
omium      0.4.0
omium-mcp  0.1.0
```

For convenience, put the venv on your PATH for this shell so you can type `omium-mcp` directly:

**macOS / Linux:**

```bash
export PATH="$HOME/omium/bin:$PATH"
```

**Windows (PowerShell):**

```powershell
$env:PATH = "$HOME\omium\Scripts;$env:PATH"
```

Set your API key without it landing in shell history:

**macOS / Linux:**

```bash
read -rs OMIUM_API_KEY && export OMIUM_API_KEY
echo "key length: ${#OMIUM_API_KEY}"   # sanity check; doesn't print the key
```

**Windows (PowerShell):**

```powershell
$secure = Read-Host "OMIUM_API_KEY" -AsSecureString
$env:OMIUM_API_KEY = [System.Net.NetworkCredential]::new("", $secure).Password
"key length: $($env:OMIUM_API_KEY.Length)"   # sanity check; doesn't print the key
```

---

## Use Omium with an AI client

Install the package, point an AI client at it, then ask questions in plain English. The AI client picks the right Omium tool itself.

### Claude Code

**macOS / Linux:**

```bash
claude mcp add omium omium-mcp --env OMIUM_API_KEY="$OMIUM_API_KEY"
claude mcp list   # should show "omium"
```

**Windows (PowerShell):**

```powershell
claude mcp add omium omium-mcp --env "OMIUM_API_KEY=$env:OMIUM_API_KEY"
claude mcp list   # should show "omium"
```

Inside Claude Code, ask:

> Show me my Omium workflows and dashboard metrics.

Claude will call the `list_workflows` and `get_dashboard_metrics` tools and render the result. To remove later: `claude mcp remove omium`.

### Claude Desktop

Edit your Claude Desktop config:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

Add an entry for Omium:

```json
{
  "mcpServers": {
    "omium": {
      "command": "omium-mcp",
      "env": {
        "OMIUM_API_KEY": "omium_..."
      }
    }
  }
}
```

Replace `omium_...` with your actual key. Restart Claude Desktop. The Omium tools will appear in the tool list.

### Cursor

In Cursor's settings, add an MCP server with the same shape: command `omium-mcp`, env var `OMIUM_API_KEY`. The exact UI varies by Cursor version — see Cursor's MCP docs for the current location.

### What you get

Tools spanning workflows, executions, checkpoints, traces, failures, projects, GitHub integration, recovery, replay, analytics, audit logs, billing, and identity. Run `omium-mcp` with `--help` to see the CLI surface; the actual tool list is enumerated by the AI client's tool-discovery step.

---

## Optional — Self-host the MCP over HTTP

For team deployments where many users share one MCP server behind a load balancer. The `omium-mcp serve` command works the same on every OS:

```
omium-mcp serve --host 0.0.0.0 --port 9100
```

Each request must carry `Authorization: Bearer <api_key>` — the server extracts the key per-request and forwards it to the Omium gateway as `X-API-Key`. There's no shared secret on the server itself.

Quick sanity check:

**macOS / Linux:**

```bash
# Without a key — should return 401
curl -i http://localhost:9100/mcp

# With a key — should accept the JSON-RPC initialize handshake
curl -X POST http://localhost:9100/mcp \
  -H "Authorization: Bearer $OMIUM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

**Windows (PowerShell):**

> Use `curl.exe` (the real curl shipped with Windows 10+), not the `curl` alias which is `Invoke-WebRequest` and behaves differently.

```powershell
# Without a key — should return 401
curl.exe -i http://localhost:9100/mcp

# With a key — JSON body via a here-string to avoid quote-escaping pain
$body = @'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}
'@
curl.exe -X POST http://localhost:9100/mcp `
  -H "Authorization: Bearer $env:OMIUM_API_KEY" `
  -H "Content-Type: application/json" `
  -d $body
```

For containerized deployments, the `omium-MCP` repo ships a `Dockerfile` you can build directly.

---

## Troubleshooting

**`pip install omium` fails with "Requires-Python >=3.10"**
Your Python is older than 3.10. Install Python 3.10+ (via `pyenv`, `uv`, your OS package manager, or python.org) and retry. Python 3.10+ is required because Omium's bundled MCP server depends on the upstream `mcp` SDK, which doesn't support older versions.

**`omium-mcp` runs but every tool returns 401**
Your `OMIUM_API_KEY` is wrong, expired, or unset. Confirm it's exported (`echo "key length: ${#OMIUM_API_KEY}"` should print > 30) and that you're using a key from the same environment as `OMIUM_API_BASE` (production keys against `https://api.omium.ai`, dev keys against your local platform).

**`omium-mcp` runs but tools return network errors**
By default the server talks to `https://api.omium.ai`. If you're pointing at a different backend (local dev, staging, self-hosted), set `OMIUM_API_BASE`:

**macOS / Linux:**

```bash
export OMIUM_API_BASE="http://localhost:8000"
```

**Windows (PowerShell):**

```powershell
$env:OMIUM_API_BASE = "http://localhost:8000"
```

**AI client doesn't see Omium tools after configuration**
Restart the client after editing its config. For Claude Code use `claude mcp list` to verify the server is registered. For Claude Desktop, fully quit and re-launch (not just close the window).

**The `omium` CLI prints the wrong version**
Cosmetic bug being tracked separately. The actual installed version is what `pip show omium` reports — that's authoritative.

---

## Cleanup

**macOS / Linux:**

```bash
unset OMIUM_API_KEY
claude mcp remove omium 2>/dev/null   # if you registered it with Claude Code
rm -rf ~/omium                         # to remove the venv
```

**Windows (PowerShell):**

```powershell
Remove-Item Env:\OMIUM_API_KEY -ErrorAction SilentlyContinue
claude mcp remove omium 2>$null              # if you registered it with Claude Code
Remove-Item -Recurse -Force $HOME\omium       # to remove the venv
```
