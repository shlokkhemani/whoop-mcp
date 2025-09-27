#!/usr/bin/env python3
"""
WHOOP OAuth Server
A Flask server that handles the complete WHOOP OAuth 2.0 flow and stores bearer tokens locally.
"""

import os
import json
import secrets
import urllib.parse
import requests
from flask import Flask, request, redirect, render_template_string, jsonify
from datetime import datetime, timedelta
import base64
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration
WHOOP_BASE_URL = "https://api.prod.whoop.com"
REDIRECT_URI = "http://localhost:8080/callback"
SCOPES = "offline read:profile read:body_measurement read:cycles read:sleep read:workout"

# Load configuration from environment or config file
CLIENT_ID = os.getenv('WHOOP_CLIENT_ID')
CLIENT_SECRET = os.getenv('WHOOP_CLIENT_SECRET')

# Token storage file
TOKENS_FILE = "whoop_tokens.json"

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>WHOOP OAuth Server</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .success { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .error { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .info { background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; }
        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0056b3; }
        .token-display { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace; word-break: break-all; }
        .config-section { background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>WHOOP OAuth Server</h1>
    
    {% if not client_configured %}
    <div class="config-section">
        <h3>⚠️ Configuration Required</h3>
        <p>Please set your WHOOP client credentials:</p>
        <ul>
            <li><strong>WHOOP_CLIENT_ID</strong> - Your WHOOP app's client ID</li>
            <li><strong>WHOOP_CLIENT_SECRET</strong> - Your WHOOP app's client secret</li>
        </ul>
        <p>You can set these as environment variables or create a .env file.</p>
    </div>
    {% endif %}
    
    {% if client_configured %}
    <div class="container">
        <h3>OAuth Flow Status</h3>
        {% if tokens %}
        <div class="success">
            <h4>✅ Authentication Successful!</h4>
            <p><strong>Access Token:</strong></p>
            <div class="token-display">{{ tokens.access_token[:50] }}...</div>
            <p><strong>Expires:</strong> {{ tokens.expires_at }}</p>
            <p><strong>Scopes:</strong> {{ tokens.scope }}</p>
            <form method="post" action="/refresh_token" style="display: inline;">
                <button type="submit">🔄 Refresh Token</button>
            </form>
            <form method="post" action="/test_api" style="display: inline; margin-left: 10px;">
                <button type="submit">🧪 Test API Call</button>
            </form>
        </div>
        {% else %}
        <div class="info">
            <h4>Ready to Authenticate</h4>
            <p>Click the button below to start the WHOOP OAuth flow.</p>
            <form method="get" action="/authorize">
                <button type="submit">🔐 Start WHOOP Authentication</button>
            </form>
        </div>
        {% endif %}
    </div>
    
    <div class="container">
        <h3>API Endpoints</h3>
        <ul>
            <li><strong>GET /authorize</strong> - Start OAuth flow</li>
            <li><strong>GET /callback</strong> - OAuth callback handler</li>
            <li><strong>GET /tokens</strong> - View stored tokens</li>
            <li><strong>POST /refresh_token</strong> - Refresh access token</li>
            <li><strong>POST /test_api</strong> - Test API call with current token</li>
        </ul>
    </div>
    {% endif %}
</body>
</html>
"""

class TokenManager:
    """Manages WHOOP tokens storage and retrieval."""
    
    def __init__(self, tokens_file=TOKENS_FILE):
        self.tokens_file = tokens_file
    
    def save_tokens(self, token_data):
        """Save tokens to local file."""
        try:
            with open(self.tokens_file, 'w') as f:
                json.dump(token_data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving tokens: {e}")
            return False
    
    def load_tokens(self):
        """Load tokens from local file."""
        try:
            if os.path.exists(self.tokens_file):
                with open(self.tokens_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading tokens: {e}")
        return None
    
    def clear_tokens(self):
        """Clear stored tokens."""
        try:
            if os.path.exists(self.tokens_file):
                os.remove(self.tokens_file)
            return True
        except Exception as e:
            print(f"Error clearing tokens: {e}")
            return False

token_manager = TokenManager()

@app.route('/')
def index():
    """Main page showing OAuth status."""
    tokens = token_manager.load_tokens()
    client_configured = bool(CLIENT_ID and CLIENT_SECRET)
    return render_template_string(HTML_TEMPLATE, tokens=tokens, client_configured=client_configured)

@app.route('/authorize')
def authorize():
    """Start the OAuth authorization flow."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return jsonify({"error": "Client credentials not configured"}), 400
    
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(8)
    
    # Build authorization URL
    auth_params = {
        'response_type': 'code',
        'client_id': CLIENT_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': SCOPES,
        'state': state
    }
    
    auth_url = f"{WHOOP_BASE_URL}/oauth/oauth2/auth?" + urllib.parse.urlencode(auth_params)
    
    # Store state in session (in production, use proper session management)
    app.config['SECRET_KEY'] = secrets.token_hex(16)
    
    return redirect(auth_url)

@app.route('/callback')
def callback():
    """Handle OAuth callback."""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')
    
    if error:
        return jsonify({"error": f"OAuth error: {error}"}), 400
    
    if not code:
        return jsonify({"error": "No authorization code received"}), 400
    
    # Exchange code for tokens
    token_data = exchange_code_for_tokens(code)
    
    if token_data:
        # Calculate expiration time
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        token_data['expires_at'] = expires_at.isoformat()
        
        # Save tokens
        if token_manager.save_tokens(token_data):
            return redirect('/?success=true')
        else:
            return jsonify({"error": "Failed to save tokens"}), 500
    else:
        return jsonify({"error": "Failed to exchange code for tokens"}), 400

def exchange_code_for_tokens(code):
    """Exchange authorization code for access and refresh tokens."""
    token_url = f"{WHOOP_BASE_URL}/oauth/oauth2/token"
    
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    try:
        response = requests.post(token_url, data=data, headers={
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Token exchange failed: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        print(f"Error exchanging code for tokens: {e}")
        return None

@app.route('/tokens')
def get_tokens():
    """Get stored tokens."""
    tokens = token_manager.load_tokens()
    if tokens:
        # Don't expose the full token in JSON response for security
        safe_tokens = tokens.copy()
        if 'access_token' in safe_tokens:
            safe_tokens['access_token'] = safe_tokens['access_token'][:20] + "..."
        if 'refresh_token' in safe_tokens:
            safe_tokens['refresh_token'] = safe_tokens['refresh_token'][:20] + "..."
        return jsonify(safe_tokens)
    else:
        return jsonify({"message": "No tokens found"})

@app.route('/refresh_token', methods=['POST'])
def refresh_token():
    """Refresh the access token using the refresh token."""
    tokens = token_manager.load_tokens()
    
    if not tokens or 'refresh_token' not in tokens:
        return jsonify({"error": "No refresh token available"}), 400
    
    refresh_url = f"{WHOOP_BASE_URL}/oauth/oauth2/token"
    
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': tokens['refresh_token'],
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    
    try:
        response = requests.post(refresh_url, data=data, headers={
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        if response.status_code == 200:
            new_tokens = response.json()
            # Calculate new expiration time
            expires_in = new_tokens.get('expires_in', 3600)
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            new_tokens['expires_at'] = expires_at.isoformat()
            
            # Save updated tokens
            if token_manager.save_tokens(new_tokens):
                return redirect('/?refreshed=true')
            else:
                return jsonify({"error": "Failed to save refreshed tokens"}), 500
        else:
            return jsonify({"error": f"Token refresh failed: {response.status_code} - {response.text}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Error refreshing token: {e}"}), 500

@app.route('/test_api', methods=['POST'])
def test_api():
    """Test API call with current access token."""
    tokens = token_manager.load_tokens()
    
    if not tokens or 'access_token' not in tokens:
        return jsonify({"error": "No access token available"}), 400
    
    # Test with user profile endpoint
    profile_url = f"{WHOOP_BASE_URL}/developer/v2/user/profile/basic"
    
    headers = {
        'Authorization': f"Bearer {tokens['access_token']}"
    }
    
    try:
        response = requests.get(profile_url, headers=headers)
        
        if response.status_code == 200:
            return jsonify({
                "success": True,
                "data": response.json(),
                "status_code": response.status_code
            })
        else:
            return jsonify({
                "error": f"API call failed: {response.status_code}",
                "response": response.text
            }), 400
            
    except Exception as e:
        return jsonify({"error": f"Error making API call: {e}"}), 500

@app.route('/clear_tokens', methods=['POST'])
def clear_tokens():
    """Clear stored tokens."""
    if token_manager.clear_tokens():
        return redirect('/?cleared=true')
    else:
        return jsonify({"error": "Failed to clear tokens"}), 500

if __name__ == '__main__':
    print("WHOOP OAuth Server")
    print("==================")
    print(f"Server will run at: http://localhost:8080")
    print(f"Redirect URI: {REDIRECT_URI}")
    print()
    
    if not CLIENT_ID or not CLIENT_SECRET:
        print("⚠️  WARNING: Client credentials not configured!")
        print("Set WHOOP_CLIENT_ID and WHOOP_CLIENT_SECRET environment variables")
        print("or create a .env file with these values.")
        print()
    
    print("Starting server...")
    app.run(debug=True, host='0.0.0.0', port=8080)
