# WHOOP OAuth Server

A Python Flask server that handles the complete WHOOP OAuth 2.0 flow and stores authenticated user bearer tokens locally.

## Features

- Complete OAuth 2.0 authorization flow
- Automatic token exchange and storage
- Token refresh functionality
- Web interface for easy interaction
- Local token storage in JSON format
- API testing capabilities

## Setup

### Quick Setup (Recommended)

```bash
# Run the setup script
./setup.sh

# Edit your credentials
nano .env  # or use your preferred editor

# Start the server
./run.sh
```

### Manual Setup

#### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Configure Client Credentials

You need to obtain your WHOOP client credentials from the WHOOP Developer Portal:

1. Go to [developer.whoop.com](https://developer.whoop.com)
2. Create a new application
3. Set redirect URI to: `http://localhost:5000/callback`
4. Note your `client_id` and `client_secret`

#### 4. Set Environment Variables

Create a `.env` file in the project directory:

```bash
cp config.env.example .env
```

Then edit `.env` with your actual credentials:

```
WHOOP_CLIENT_ID=your_actual_client_id
WHOOP_CLIENT_SECRET=your_actual_client_secret
```

## Usage

### Using Scripts (Recommended)

```bash
# Start the server
./run.sh
```

### Manual Start

```bash
# Activate virtual environment
source venv/bin/activate

# Start the server
python whoop_oauth_server.py
```

The server will start at `http://localhost:8080`

### OAuth Flow

1. **Open the web interface**: Navigate to `http://localhost:8080`
2. **Start authentication**: Click "Start WHOOP Authentication"
3. **Authorize**: You'll be redirected to WHOOP's authorization page
4. **Login and consent**: Log in to your WHOOP account and grant permissions
5. **Automatic callback**: The server will handle the callback and store your tokens

### API Endpoints

- `GET /` - Main web interface
- `GET /authorize` - Start OAuth flow
- `GET /callback` - OAuth callback handler (automatic)
- `GET /tokens` - View stored tokens (JSON)
- `POST /refresh_token` - Refresh access token
- `POST /test_api` - Test API call with current token
- `POST /clear_tokens` - Clear stored tokens

### Using the Stored Tokens

Tokens are stored in `whoop_tokens.json` in the project directory. The file contains:

```json
{
  "access_token": "eyJhbGciOi...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "def50200...",
  "scope": "offline read:profile read:sleep ...",
  "expires_at": "2024-01-01T12:00:00"
}
```

### Making API Calls

You can use the stored access token to make API calls to WHOOP:

```python
import requests
import json

# Load tokens
with open('whoop_tokens.json', 'r') as f:
    tokens = json.load(f)

# Make API call
headers = {'Authorization': f"Bearer {tokens['access_token']}"}
response = requests.get('https://api.prod.whoop.com/developer/v2/user/profile/basic', headers=headers)
print(response.json())
```

## OAuth Scopes

The server requests the following scopes:
- `offline` - Allows refresh token usage
- `read:profile` - Read user profile information
- `read:body_measurement` - Read body measurement data
- `read:cycles` - Read recovery and strain cycles
- `read:sleep` - Read sleep data
- `read:workout` - Read workout data

## Security Notes

- Tokens are stored locally in plain text JSON
- The server runs on localhost only by default
- State parameter is used for CSRF protection
- Tokens include expiration information

## Troubleshooting

### Common Issues

1. **"Client credentials not configured"**
   - Make sure you've set `WHOOP_CLIENT_ID` and `WHOOP_CLIENT_SECRET`
   - Check that your `.env` file is in the correct location

2. **"OAuth error" during authorization**
   - Verify your redirect URI matches exactly: `http://localhost:5000/callback`
   - Check that your client credentials are correct

3. **"Failed to exchange code for tokens"**
   - Ensure your client secret is correct
   - Check that the authorization code hasn't expired

4. **"API call failed"**
   - Your access token may have expired - try refreshing
   - Verify the token has the required scopes

### Debug Mode

The server runs in debug mode by default. For production use, set `debug=False` in the `app.run()` call.

## Example WHOOP API Calls

Once you have a valid access token, you can make calls to various WHOOP API endpoints:

```python
# User profile
GET https://api.prod.whoop.com/developer/v2/user/profile/basic

# Sleep data
GET https://api.prod.whoop.com/developer/v2/activity/sleep

# Workout data  
GET https://api.prod.whoop.com/developer/v2/activity/workout

# Recovery data
GET https://api.prod.whoop.com/developer/v2/cycle/recovery
```

All requests require the `Authorization: Bearer YOUR_ACCESS_TOKEN` header.
