"""Interactive setup wizard — `omium-mcp init`.

Walks a fresh user through: pasting an API key, validating it against the
Omium platform, and (optionally) wiring it into Claude Code via `claude mcp
add`. Designed so v1 only auto-configures Claude Code; manual instructions
are printed for Claude Desktop and Cursor.

No client config is written until the API key has been verified, so a bad
key never leaves a half-configured machine.
"""

from __future__ import annotations

import getpass
import os
import shutil
import subprocess
import sys
from typing import Any

import httpx

from .config import OMIUM_API_BASE


_VERIFY_PATH = "/api/v1/api-keys/verify"


def _omium_mcp_binary() -> str:
    """Absolute path to the `omium-mcp` script in the *current* venv.

    pip installs the console script next to the Python interpreter, so we
    derive the path from `sys.executable` rather than relying on PATH. This
    matters because Claude Code spawns MCP servers in its own subprocess
    environment whose PATH may not include the venv this wizard runs in.
    """
    bindir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(bindir, "omium-mcp")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    # Windows wheels install console scripts as .exe in Scripts\
    win_candidate = candidate + ".exe"
    if os.path.isfile(win_candidate) and os.access(win_candidate, os.X_OK):
        return win_candidate
    # Fallback: bare name, pray PATH covers it (best-effort, not guaranteed
    # to work when launched by Claude Code).
    return "omium-mcp"


def _verify_key(key: str) -> dict[str, Any] | None:
    """Hit /api/v1/api-keys/verify with the pasted key. Returns identity dict on
    success, None on auth failure or network error. Prints the failure reason."""
    try:
        r = httpx.get(
            f"{OMIUM_API_BASE}{_VERIFY_PATH}",
            headers={"X-API-Key": key},
            timeout=10.0,
        )
    except httpx.RequestError as e:
        print(f"  Network error contacting {OMIUM_API_BASE}: {e}", file=sys.stderr)
        return None

    if r.status_code == 200:
        try:
            return r.json()
        except ValueError:
            return {}

    if r.status_code in (401, 403):
        print("  Key rejected by the server (401/403). Check the key and try again.", file=sys.stderr)
    else:
        print(f"  Unexpected response from {OMIUM_API_BASE}: HTTP {r.status_code}", file=sys.stderr)
    return None


def _print_identity(identity: dict[str, Any]) -> None:
    """Best-effort pretty-print of whatever the verify endpoint returned."""
    interesting = ("tenant_name", "tenant_slug", "tenant", "role", "scopes", "user", "email")
    shown = False
    for field in interesting:
        if field in identity and identity[field]:
            value = identity[field]
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            print(f"  {field.replace('_', ' ').title():<14} {value}")
            shown = True
    if not shown and identity:
        # Fall back to dumping the first few fields so the user sees *something*.
        for k, v in list(identity.items())[:4]:
            print(f"  {k}: {v}")


def _add_to_claude_code(key: str) -> tuple[bool, str]:
    """Run `claude mcp add --scope user omium <abs-path> --env OMIUM_API_KEY=<key>`.

    Adds at user scope so the Omium tools are visible in every project, not
    just the cwd Claude Code was launched from.
    Returns (success, message).
    """
    binary = _omium_mcp_binary()
    try:
        result = subprocess.run(
            [
                "claude", "mcp", "add",
                "--scope", "user",
                "omium", binary,
                "--env", f"OMIUM_API_KEY={key}",
            ],
            capture_output=True,
            text=True,
            timeout=15.0,
        )
    except FileNotFoundError:
        return False, "claude CLI disappeared from PATH between detection and execution"
    except subprocess.TimeoutExpired:
        return False, "`claude mcp add` did not complete within 15s"

    if result.returncode == 0:
        return True, ""

    stderr = (result.stderr or result.stdout or "").strip()
    if "already" in stderr.lower() or "exists" in stderr.lower():
        return False, (
            "Claude Code already has an 'omium' MCP server configured.\n"
            "  Remove from any scope it lives in, then re-run init:\n"
            "    claude mcp remove omium -s user\n"
            "    claude mcp remove omium -s local    # if also at local scope\n"
            "    claude mcp remove omium -s project  # if committed in a project's .mcp.json"
        )
    return False, f"`claude mcp add` failed (exit {result.returncode}): {stderr or '<no output>'}"


def _print_manual_instructions(key: str) -> None:
    """Fallback when the `claude` CLI isn't available — show the user what to
    paste into Claude Desktop / Cursor / their preferred client."""
    print()
    print("Manual setup (Claude Desktop / Cursor / other MCP clients):")
    print()
    print("  Set the env var in your shell, then add this MCP server entry:")
    print()
    print('  {')
    print('    "mcpServers": {')
    print('      "omium": {')
    print('        "command": "omium-mcp",')
    print(f'        "env": {{ "OMIUM_API_KEY": "{key[:6]}…{key[-4:] if len(key) > 10 else ""}" }}')
    print('      }')
    print('    }')
    print('  }')
    print()
    print("  Replace the truncated key above with the full value you just pasted.")
    print("  Config file locations:")
    print("    macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("    Linux:   ~/.config/Claude/claude_desktop_config.json")
    print("    Windows: %APPDATA%\\Claude\\claude_desktop_config.json")
    print()
    print("  Full guide: https://pypi.org/project/omium-mcp/")


def run_init() -> int:
    """Entry point — orchestrates the whole wizard. Returns a process exit code."""
    print("Welcome to Omium! Let's get you set up.\n")
    print(f"Get your API key from your Omium dashboard, then paste it below.")
    print(f"(API base: {OMIUM_API_BASE})\n")

    try:
        key = getpass.getpass("Paste your Omium API key (input hidden): ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 1

    if not key:
        print("No key entered. Aborting.", file=sys.stderr)
        return 1

    print("\nVerifying key...")
    identity = _verify_key(key)
    if identity is None:
        return 1

    print("  ✓ valid")
    _print_identity(identity)

    # Detect Claude Code
    print("\nLooking for installed AI clients...")
    if shutil.which("claude") is None:
        print("  Claude Code CLI not found on PATH — skipping automatic configuration.")
        _print_manual_instructions(key)
        return 0

    print("  ✓ Claude Code detected")

    try:
        answer = input("\nConfigure Claude Code with your Omium key? [Y/n]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. No config files were written.", file=sys.stderr)
        return 1

    if answer in ("n", "no"):
        print("Skipped. Run `claude mcp add omium omium-mcp --env OMIUM_API_KEY=<key>` later.")
        return 0

    ok, message = _add_to_claude_code(key)
    if not ok:
        print(f"\n✗ {message}", file=sys.stderr)
        return 1

    print("  ✓ Added 'omium' MCP server to Claude Code")
    print("\n✓ Setup complete!")
    print("\nOpen Claude Code and try asking:")
    print('  "show me my Omium workflows"')
    print()
    return 0


if __name__ == "__main__":
    sys.exit(run_init())
