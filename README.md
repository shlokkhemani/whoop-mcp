# WHOOP MCP Server

FastMCP server that wraps WHOOP OAuth and publishes four tools for daily recovery, activity history, trends, and basic profile data. Built to plug directly into Poke once hosted.

## Requirements
- Python 3.10
- WHOOP developer app with scopes: `offline`, `read:profile`, `read:body_measurement`, `read:cycles`, `read:recovery`, `read:sleep`, `read:workout`
- Redirect URI registered in WHOOP: `http://localhost:9000/auth/callback` for local work (add your hosted URL later)

## Local development (optional)
```bash
python3.10 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt fastmcp httpx
cp .env.example .env
```
Set these variables in `.env`:
- `WHOOP_CLIENT_ID`
- `WHOOP_CLIENT_SECRET`
- `PUBLIC_BASE_URL=http://localhost:9000`
- `OAUTH_REDIRECT_PATH=/auth/callback`

Run the server with `python whoop_mcp_server.py` and visit `http://localhost:9000/.well-known/oauth-authorization-server` to confirm it is live. Connect from FastMCP Inspector if you want to test locally.

## Hosting for Poke
Poke only connects to hosted MCP servers. One path:
1. Push this project to your Git provider (exclude any local helpers or token files).
2. In [FastMCP Cloud](https://gofastmcp.com/), sync the repo.
3. Set the entry point to `whoop_mcp_server.py`.
4. Add environment variables (`WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `PUBLIC_BASE_URL=https://<your-fastmcp-domain>`, `OAUTH_REDIRECT_PATH=/auth/callback`).
5. In the WHOOP developer console, add the hosted redirect (`https://<your-fastmcp-domain>/auth/callback`).
6. Deploy. FastMCP Cloud stores tokens per environment.
7. In Poke, open https://poke.com/settings/connections/integrations/new and paste your hosted MCP URL. Authenticate with WHOOP when prompted.

## Tools exposed
- `get_daily_update`
- `get_activities`
- `get_trends`
- `get_user_profile`

Keep `.env` out of version control. Rotate WHOOP credentials if you suspect leakage.
