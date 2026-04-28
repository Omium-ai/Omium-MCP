# Omium MCP — Quickstart

Try Omium's 84 tools (workflows, executions, traces, billing, …) from inside
Claude Code or Claude Desktop in 2 minutes.

## You need

- **Docker** (Docker Desktop on macOS/Windows, or `docker.io` on Linux).
- **An Omium API key.** Log into https://app.omium.ai → Settings → API Keys →
  *Create*. Copy the `omium_...` value.
- **Claude Code** or **Claude Desktop** installed.

## 1. Start the MCP

```bash
docker run -d --name omium-mcp -p 9100:9100 bhav55/omium-mcp:latest
```

That's it. Container pulls (~55 MB), boots in ~2s, listens on
`http://localhost:9100/mcp`. It talks to production `api.omium.ai` out of the
box — no env vars, no config file.

> On Apple Silicon (M1/M2/M3) you'll see a one-time Rosetta warning; safe to
> ignore. Add `--platform linux/amd64` to silence it.

## 2. Wire into your Claude client

### Claude Code

```bash
claude mcp add --transport http omium http://localhost:9100/mcp \
  --header "Authorization: Bearer omium_YOUR_KEY_HERE"
```

Check it's loaded:
```bash
claude mcp list
```
Inside Claude Code, `/mcp` should show `omium` with 84 tools.

### Claude Desktop

Edit the config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `~/.config/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "omium": {
      "type": "http",
      "url": "http://localhost:9100/mcp",
      "headers": {
        "Authorization": "Bearer omium_YOUR_KEY_HERE"
      }
    }
  }
}
```

Restart Claude Desktop.

## 3. Try it

Ask Claude:

> "List my Omium workflows."
> "Show me the last 5 executions and their status."
> "What's my credit balance and subscription status?"
> "Create a new execution against workflow `<workflow_id>`."

Claude will call the right MCP tool, hit `api.omium.ai`, and return structured
results.

## Update the MCP to the latest version

```bash
docker pull bhav55/omium-mcp:latest
docker rm -f omium-mcp
docker run -d --name omium-mcp -p 9100:9100 bhav55/omium-mcp:latest
```

## Stop it

```bash
docker stop omium-mcp
```

Start again:
```bash
docker start omium-mcp
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `401 Unauthorized` on every call | Bearer header missing or API key wrong. Re-copy from app.omium.ai. |
| `Port 9100 is already allocated` | Use another host port: `-p 9200:9100` and update the URL in your Claude config to `:9200`. |
| `Cannot connect to host api.omium.ai` | Corporate proxy / VPN blocking outbound HTTPS. Test with `docker exec omium-mcp curl -I https://api.omium.ai/api/v1/health`. |
| Some tools return `500 Internal Server Error` | Expected for a handful of endpoints (replay, checkpoint proto, workflow cost, search audit) — platform-side bugs in flight. The rest of the ~90 tools work. |
| Tools don't appear in Claude | `docker logs omium-mcp` to see if it booted; `/mcp` inside Claude Code to reload. |

## What's inside

- **14 categories of tools**: identity, workflows, executions, checkpoints,
  failures, scores, traces, projects, GitHub, recovery, replay,
  analytics, audit, billing.
- **Auth**: your API key goes in once in the Claude config; the MCP forwards it
  to Kong as `X-API-Key`. Your tenant scope is derived server-side.
- **Image**: `bhav55/omium-mcp` on Docker Hub — https://hub.docker.com/r/bhav55/omium-mcp

## Feedback / bugs

NO NEED TO Ping @bhavjain with `docker logs omium-mcp` output if something's off.
