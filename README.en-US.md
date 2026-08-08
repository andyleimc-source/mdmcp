

# mdymcp

> ## ⬆️ Upgrade for Existing Users
>
> **Upgrade via installer (recommended, bypasses occasional uv index cache update issues):**
> ```bash
> uv tool install --force --refesh mdymcp
> ```
> (Or `uv tool upgrade mdymcp`; restart your IDE / reopen the session after upgrading.)
>
> ### 0.5.x (Centralized v1 token refresh for multiple machines)
> **Single-machine users**: Simply upgrade the tool, **no changes needed** (defaults to local refresh, fully backward compatible).
>
> **Multiple machines/servers sharing the same Mingdao account**: You must switch to "Server Centralized Refresh". Reason: when multiple endpoints independently hold and refresh tokens, Mingdao rotates the `refresh_token` on every refresh, causing them to orphan each other (`error_code 10101`).
> Centralize refreshing on one persistent server as the sole owner, making other endpoints read-only: on the machine performing the initial deployment, run `mdymcp-install` and select `[2] Server Centralized` (or `mdymcp-server-setup`). Copy the generated `~/.mdymcp/server_token_key` and the 4 `MD_V1_TOKEN_*` variables from `.env` to the other machines (**do not re-authorize on those machines**). See [`server/README.md`](server/README.md) for details.
> > ⚠️ If a project's own venv also `import mdymcp` (instead of only using the global binary), upgrade it separately:
> > `uv pip install --python <project>/.venv/bin/python -U mdymcp`.
>
> ### 0.3.0 (HAP switched to Personal PAT) — Only required for users still on 0.2.x
> Starting from 0.3.0, HAP uses a Personal PAT instead of the old `refresh_token / hap_key`. Generate a PAT (starts with `pat_`) at <https://www.mingdao.com/personal?type=pat>, then choose one of the following:
> - **Easiest**: Re-run `mdymcp-install` and paste it when prompted at the HAP step;
> - **Manual**: Edit `~/.mdymcp/.env`, **remove** `MD_HAP_KEY` / `MD_HAP_REFRESH_TOKEN` / `MD_HAP_TOKEN`, and **add** `MD_HAP_PAT=pat_xxx`.

## One-Click Installation

**macOS / Linux**
```bash
curl -LsSf https://raw.githubusercontent.com/andyleimc-source/mdymcp/main/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -c "irm https://raw.githubusercontent.com/andyleimc-source/mdymcp/main/install.ps1 | iex"
```

The script performs three actions:
1. Checks for `uv` and installs it from the official source if missing (uv automatically pulls the appropriate Python version, so it doesn't matter if you have 3.14, 3.9, or nothing installed)
2. `uv tool install mdymcp`
3. Launches the `mdymcp-install` interactive wizard — browser OAuth for v1 credentials → auto-opens the HAP Personal PAT page to paste `MD_HAP_PAT` → prompts you to select scope (user-level/project-level/both) + multi-select IDEs to register via numbers → automatically installs the mdymcp skill (usage mindset + troubleshooting SOP) to `~/.claude/skills/mdymcp/` when Claude Code is detected

Configuration is written to `~/.mdymcp/.env` (Windows: `%USERPROFILE%\.mdymcp\.env`), making it usable across directories.

To re-run the setup after installation: `mdymcp-install`

---

## Features

**Unified MCP Server for Mingdao** —— One installation, **98 tools**:

- **v1 Collaboration API (50 tools, locally implemented)**: Feeds / Schedules / Direct Messages / Inbox / Groups / Users / Organizations / Personal Accounts
- **HAP Gateway (48 tools, transparent proxy via `api2.mingdao.com/mcp`)**: Apps / Worksheets / Records / Role Members / Workflow Approvals / Charts / Option Sets / Knowledge Bases / Regional Organizations

HAP tools are dynamically provided by the remote gateway; the exact parameter schemas are based on what `tools/list` returns at startup.

## Supported AI IDEs

| IDE | Config File | Supported Scope |
|-----|---------|---------|
| **Claude Code** | `~/.claude.json` (via `claude mcp add`) | User-level + Project-level `.mcp.json` |
| **Codex CLI** | `~/.codex/config.toml` | User-level |
| **Cursor** | `~/.cursor/mcp.json` | User-level + Project-level `.cursor/mcp.json` |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` | User-level |
| **Gemini Antigravity** | `~/.gemini/antigravity/mcp_config.json` | User-level |
| **Trae** (including Trae CN) | mac: `~/Library/Application Support/Trae/User/mcp.json`<br>win: `%APPDATA%\Trae\User\mcp.json`<br>linux: `~/.config/Trae/User\mcp.json` | User-level |
| **VS Code** (Copilot Chat) | `.vscode/mcp.json` | Project-level |

`mdymcp-install` automatically detects installed IDEs; you just need to answer two prompts for scope and clients. To specify manually: `mdymcp-install --client=cursor,windsurf,trae` (`--client=all` installs for all).

> **Antigravity**: After configuration, go to "Manage MCP Servers → Refresh" in the IDE to see mdymcp.
>
> **Cursor / Windsurf / Trae / VS Code**: Usually requires restarting the IDE or manually refreshing in the MCP settings.

---

## How to Get the HAP PAT

> When `mdymcp-install` reaches the HAP step, it will **automatically open your browser** to the PAT page. Just copy and paste.

PAT Page: <https://www.mingdao.com/personal?type=pat>

- **Already logged in** → Generate/manage your Personal PAT directly on the page (starts with `pat_`).
- **Not logged in** → Log in first, and you will be redirected back to this page.

Copy `pat_xxx` and paste it when the wizard prompts `MD_HAP_PAT:`. The PAT acts as a Bearer token, is valid long-term, and can be revoked/regenerated by you at any time without server-side exchange. Leave it blank to skip HAP and use only v1 tools.

---

## Architecture & Tokens

```
┌──────────────────────┐ stdio ┌──────────────────────────────┐
│ Claude Code / Cursor │──────▶│        mdymcp.server         │
│ / Codex / Windsurf / │       ├──────────────────────────────┤
│ Antigravity / Trae / │       │ [Static Registration] 50 v1  │──┐
│ VS Code Copilot      │       │        Tools                │  │HTTP
└──────────────────────┘       ├──────────────────────────────┤  │
                               │ [Dynamic Registration]      │──┤
                               │ HapGateway                  │  │
                               │ 48 HAP Tools (Transparent   │  │
                               │        Proxy)              │  ▼
                               └──────────────────────────────┘
                             ┌──────────────────────────────────────┐
                             │ api.mingdao.com/v1/*   (v1 API)      │
                             │ api2.mingdao.com/mcp   (HAP gateway) │
                             └──────────────────────────────────────┘
```

| | v1 access_token | HAP Token |
|---|---|---|
| During install | Local OAuth → token saved to `~/.mdymcp/v1_token.json` | Paste PAT → `MD_HAP_PAT` saved to `.env` |
| At runtime | Local token file, renewed locally with refresh_token upon expiration | Uses `MD_HAP_PAT` directly, no remote exchange |
| Cache TTL | Follows `expires_in` from Mingdao (7 days for published apps) | Not required (PAT is the token) |

The v1 token stays entirely local: `mdymcp-auth` authorizes once to get the `access_token` + `refresh_token`, saving them to disk (chmod 600). Upon expiration, it automatically renews using the `refresh_token` (valid for 14 days). Re-authorization is only needed when the refresh token also expires. `app_key`/`app_secret` are embedded in the package (public client mode, similar to Google/GitHub CLI), requiring zero configuration. Machines with old credentials (`MD_ACCOUNT_ID`/`MD_KEY`) that haven't been authorized will fall back to the legacy remote hook chain. HAP uses the PAT from `.env` directly as a Bearer token. If the HAP gateway handshake fails, the **server does not crash**; it only skips remote tool registration, while v1 tools remain available.

**Multiple machines sharing the same account? Use server mode.** Multiple machines/servers holding the same token pair will compete to refresh (Mingdao rotates the `refresh_token` on every refresh), orphaning each other (`error_code 10101`). Centralize refreshing on one persistent server as the sole owner: run `mdymcp-server-setup` once (or `bash server/provision.sh <IP> <user>`), and the other machines will be read-only and never refresh. See [`server/README.md`](server/README.md) for details.

---

## Configuration

`~/.mdymcp/.env` (or the env block in each IDE's MCP JSON):

```env
# HAP Gateway PAT (generated at https://www.mingdao.com/personal?type=pat, starts with pat_)
MD_HAP_PAT=  # Paste during install; leave blank = skip HAP

# Optional (usually leave as is)
# MD_APP_KEY= / MD_APP_SECRET=<replace with your own OAuth app>
# MD_CALLBACK_PORT=8080
# Legacy fallback (only used if MD_APP_SECRET is not configured)
# MD_ACCOUNT_ID= / MD_KEY= / MD_HOOK_URL=
```

---

## Troubleshooting

| Symptom | Solution |
|------|------|
| `command not found: uv` | Restart the terminal; or run `export PATH="$HOME/.local/bin:$PATH"` |
| curl / irm fails to fetch astral.sh | Use a proxy; or download the tarball from <https://github.com/astral-sh/uv/releases> and manually extract it to `~/.local/bin/` |
| `irm \| iex` throws execution policy error on Windows | Admin PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `[v1] No local token available` / `Token refresh failed` | Run `mdymcp-auth` to re-authorize (refresh_token expires if unused for 14 days) |
| `Missing MD_HAP_PAT` / `PAT invalid or expired` | Regenerate the PAT at <https://www.mingdao.com/personal?type=pat>, update `MD_HAP_PAT` in `.env`, or re-run `mdymcp-install` |
| mdymcp not visible in IDE | Restart the IDE; or click Refresh in the IDE's MCP settings. If launching via GUI fails to find `uvx`, launch the IDE from the terminal instead (absolute paths should already avoid this) |
| Startup shows `0 HAP gateway tools` | `/mcp` handshake failed (likely network issue); v1 tools are unaffected |
| HAP tools return `Http Headers verification failed` | Known issue with the HAP backend (also affects Node version); not an mdymcp bug |

---

## API Reference

Mingdao Open Platform: <https://open.mingdao.com/document>

## License

MIT
