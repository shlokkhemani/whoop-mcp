# WHOOP MCP Server

FastMCP server that wraps WHOOP's OAuth flow and exposes a handful of Poke-ready tools (`get_daily_update`, `get_activities`, `get_trends`, `get_user_profile`). Use it as a reference implementation or deploy it as-is for your own account.

**Want the full story?** The accompanying blog post on building Poke integrations covers architecture, MCP client behavior, and tool design philosophy in detail.

## What you need
- Python 3.10+
- WHOOP developer app with `offline`, `read:profile`, `read:body_measurement`, `read:cycles`, `read:recovery`, `read:sleep`, `read:workout`
- Redirect URI registered in WHOOP: `http://localhost:9000/auth/callback` (add your hosted URL later if you deploy)

## Setup (local)
```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt fastmcp httpx
cp .env.example .env
```
Fill in `.env` with your WHOOP client ID, secret, and the base URL (`http://localhost:9000` for local work). Never commit this file.

## Run & authorize
```bash
python whoop_mcp_server.py
```
1. Open `http://localhost:9000/.well-known/oauth-authorization-server` to confirm the server is up.
2. Connect it from Poke (or FastMCP Inspector via `npx --yes fastmcp inspector --server http://localhost:9000`).
3. Sign into WHOOP when prompted; tokens refresh automatically after that.


## Host on FastMCP Cloud
- Push this repo to GitHub (omit local helpers like `whoop_oauth_server.py`).
- In [FastMCP Cloud](https://gofastmcp.com/), connect your Git account and select the repo.
- Set the entry point to `whoop_mcp_server.py` in the deployment settings.
- Add required environment variables (`WHOOP_CLIENT_ID`, `WHOOP_CLIENT_SECRET`, `PUBLIC_BASE_URL`, `OAUTH_REDIRECT_PATH`) in the cloud dashboard.
- Update the WHOOP developer app with the FastMCP callback URL (`https://<your-fastmcp-subdomain>/auth/callback`).
- Redeploy after editing tool code or scopes; FastMCP Cloud handles token storage per environment.

## Deploying later?
- Point `PUBLIC_BASE_URL` at your HTTPS origin and add the matching redirect in the WHOOP console.
- Keep `whoop_tokens.json` and your `.env` outside source control.
- Follow the guidance in the blog post for tool evolution, rate limiting, and MCP best practices.
