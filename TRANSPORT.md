# Why Omium MCP uses HTTP, not a stdio JSON config

This doc explains a design choice: the Omium MCP server is a long-lived HTTP
service, not a subprocess launched from an `.mcp.json` / `claude_desktop_config.json`
entry. If you've written MCP servers before and are wondering where the
familiar `"command": "python", "args": [...]` block went, this is for you.

---

## TL;DR

| | Classic stdio MCP | Omium MCP (this repo) |
|---|---|---|
| Transport | stdio pipes | Streamable HTTP (`/mcp` on :9100) |
| Server lifecycle | Client spawns a subprocess per connection | Docker container, `restart: unless-stopped` |
| Config lives in | `.mcp.json` on each client | `docker-compose.yml` + env + server code |
| Identity per call | Baked into the spawn env | `Authorization: Bearer` per request |
| Tenants served | 1 per process | N concurrent, isolated by key |

Omium is multi-tenant, so the server has to be too. Stdio can't express that
cleanly; HTTP can.

---

## What the JSON file did in stdio MCP

A typical stdio registration looks like this:

```json
{
  "mcpServers": {
    "omium": {
      "command": "python",
      "args": ["server.py"],
      "env": {
        "OMIUM_API_KEY": "omium_abc..."
      }
    }
  }
}
```

That small block carried **four** responsibilities:

1. **Process lifecycle** — the client forks `python server.py` as a subprocess
   and owns its start / stop.
2. **Environment** — any config or secrets the server needs must be in
   `env`; it's handed to the child at spawn time.
3. **Transport choice** — stdio is implicit. No URL, no port, just pipes.
4. **Identity** — whoever launched the process *is* the user for every
   tool call. One key per process.

The client owns everything; the server is a dumb child.

---

## Why stdio doesn't fit Omium

Omium has many tenants (Acme, Globex, Initech, …), each with their own
`omium_...` API key. Under the stdio model, serving all of them means:

- One Python subprocess **per tenant**
- One `.mcp.json` entry **per tenant** on every client machine
- No shared container, no shared connection pool, no shared cache
- Rolling an update = restarting N processes instead of one

More importantly, the stdio model puts the **secret in the client's config
file**. Every user needs their key embedded locally. Rotating a key means
editing every client's JSON. That's the opposite of how every other SaaS
API on the internet works.

---

## What we built instead

`server.py` uses FastMCP's **Streamable HTTP** transport:

```python
app = mcp.streamable_http_app()          # server.py:114
app.add_middleware(BearerAuthMiddleware) # server.py:115
uvicorn.run(app, host=MCP_HOST, port=MCP_PORT)
```

The container listens on `:9100/mcp`. Clients connect once, send many
requests, and carry their identity in an `Authorization: Bearer omium_...`
header on each request. The middleware (`server.py:33-74`) extracts that
token into a `ContextVar`; `_omium_get` (`server.py:77-88`) pulls it out
and forwards it as `X-API-Key` to Kong. Tenant scope is resolved
server-side from the key — the client never names a tenant.

```
Acme user   --Bearer omium_acme--→  ┐
Globex user --Bearer omium_glx--→   ├──→ [ one omium-mcp container ] ──→ Kong
Initech     --Bearer omium_ini--→   ┘
```

One deployment, many tenants, kept apart by per-request credentials.

---

## Role-by-role replacement

The JSON file's four jobs didn't disappear — they moved:

| JSON's old job | Where it lives now |
|---|---|
| Spawn the process | `docker-compose.yml` — `restart: unless-stopped` |
| Server env / config | `docker-compose.yml` `environment:` block + `.env.example` |
| Pick transport | `streamable_http_app()` in `server.py:114` |
| Carry the secret | `BearerAuthMiddleware`, per-request Bearer token |

The **client** still needs a small config entry — just a pointer, not a
launcher:

```json
{
  "mcpServers": {
    "omium": {
      "type": "http",
      "url": "http://localhost:9100/mcp",
      "headers": { "Authorization": "Bearer omium_YOUR_KEY" }
    }
  }
}
```

Or the equivalent `claude mcp add --transport http ...` one-liner (see
README). The difference: this entry is **pointer + credential**, not
**command + env**. The server is already running; the client just dials in.

---

## Trade-offs

**What we gain**

- One container serves all tenants; one place to deploy, log, monitor.
- Secrets live with the caller, not in every client's config file.
- Key rotation is a backend change — no client reconfig needed.
- Kong sits in front as the single policy / rate-limit enforcement point.
- Matches how the rest of the Omium platform already authenticates.

**What we give up**

- Not zero-install. Users need the container running (or a deployed URL)
  before they can use the MCP.
- The server is now network-reachable. Port exposure, TLS, and auth
  enforcement matter in a way they don't for a local subprocess.
- Slightly more moving parts: Docker network, Kong, uvicorn, FastMCP's
  HTTP app — versus "python server.py" on a pipe.

For a personal-tool MCP (one user, one key, runs on their laptop), stdio
is still the right shape. For a platform that already has tenants, APIs,
and a gateway, HTTP is the natural extension.

---

## When you'd still use stdio + JSON

- Local-only developer tools with no backend (a filesystem browser, a
  git helper).
- Single-user contexts where the secret in `env` is *your* secret.
- Experiments where container overhead isn't worth it.

Omium is none of those, so HTTP it is.
