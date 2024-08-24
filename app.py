"""
A simple webserver for TikTok login redirect when requesting an authorization code and scoped access token.

References:
Login/Authorization:
    https://developers.tiktok.com/doc/login-kit-desktop/

Token:
    https://developers.tiktok.com/doc/oauth-user-access-token-management/
"""

from flask import Flask, redirect, request, session, url_for
import hashlib, base64, os, requests, urllib.parse, random
import json
from datetime import datetime, timedelta
from utils import log_error
from config import CLIENT_KEY, CLIENT_SECRET , REDIRECT_URI, USER_TOKEN_FILENAME

app = Flask(__name__)
app.secret_key = os.urandom(24)

def generate_code_verifier(min=43, max=128):
    """Generate code verifier per tiktok's guidelnies"""
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    return ''.join(random.choice(characters) for _ in range(random.choice(range(min,max))))

def generate_code_challenge(verifier):
    """Generate code challenge from the code verifier using SHA256 and hex encoding."""
    sha256_hash = hashlib.sha256(verifier.encode()).hexdigest() 
    return sha256_hash

# Storing data in json file locally for now.
def load_tokens(filename=USER_TOKEN_FILENAME):
    """Load tokens from the JSON file"""
    if os.path.exists(filename):
        with open(filename, 'r') as f:
            return json.load(f)
    return {}

def save_tokens(data, filename=USER_TOKEN_FILENAME):
    """Save tokens to JSON file"""
    try:
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"[Error]: {e}")

def save_token_data(response, open_id):
    """
    Saves token data after user authorization.
    Adds expiration dates for access and refresh tokens based on request time.
    """
    datetime_now = datetime.now()

    expires_in = response.get('expires_in')
    refresh_expires_in = response.get('refresh_expires_in')

    if expires_in is not None:
        expires_in_datetime = datetime_now + timedelta(seconds=expires_in)
        response['expires_in_datetime'] = expires_in_datetime.isoformat()
    else:
        print(f"[Warning]: 'expires_in' not found for user {open_id}.")

    if refresh_expires_in is not None:
        refresh_expires_in_datetime = datetime_now + timedelta(seconds=refresh_expires_in)
        response['refresh_expires_in_datetime'] = refresh_expires_in_datetime.isoformat()
    else:
        print(f"[Warning]: 'refresh_expires_in' not found for user {open_id}.")

    response['open_id'] = open_id 

    data = load_tokens()
    data[open_id] = response 
    save_tokens(data)

def check_and_refresh_tokens():
    """Check for expired tokens and refresh if possible"""
    data = load_tokens()
    for open_id, token_data in data.items():
        refresh_token = token_data.get('refresh_token')
        expires_in_datetime = datetime.fromisoformat(token_data['expires_in_datetime'])
        refresh_expires_in_datetime = datetime.fromisoformat(token_data['refresh_expires_in_datetime'])
        
        # Check if access token is expired
        if datetime.now() >= expires_in_datetime:
            # Check if refresh token is still valid 
            if datetime.now() < refresh_expires_in_datetime:
                new_token_response = refresh_access_token(refresh_token, open_id)
                if new_token_response:
                    print(f"Token refreshed successfully for user {open_id}")
                else:
                    print(f"Failed to refresh token for user {open_id}")
            else:
                print(f"Refresh token expired for user {open_id}. Re-authentication required.")

# Refreshing tokens is a simple post request since it does not require redirect
def refresh_access_token(refresh_token, open_id):
    """Function to refresh access token using refresh token (without needing user to auth again)."""
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    token_data = {
        'client_key': CLIENT_KEY,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }

    token_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'no-cache'
    }

    response = requests.post(token_url, data=token_data, headers=token_headers)
    
    if response.status_code == 200:
        token_response = response.json()

        if 'error' in token_response:
            log_error(f"Error for user: {open_id} , Response: {token_response['error_description']}")
            return None

        save_token_data(token_response, open_id)
        return token_response
    else:
        log_error(f"Failed to refresh access token for user {open_id} , Response: {response.text}")
        return None



### Routes ###

@app.route('/')
def home():
    return '<a href="/login">Login with TikTok</a>'

@app.route('/login')
def login():
    # Create code challenge per TikTok guideline
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)


    session['code_verifier'] = code_verifier
    csrf_state = base64.urlsafe_b64encode(os.urandom(16)).decode('utf-8').rstrip('=')
    session['csrf_state'] = csrf_state

    session.modified = True  

    authorization_url = (
        "https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={urllib.parse.quote(CLIENT_KEY)}"
        f"&response_type=code"
        f"&scope=user.info.basic,video.publish,video.upload"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&state={csrf_state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    
    return redirect(authorization_url)

@app.route('/callback/')
def callback():
    # Retrieve code and state from request
    code = request.args.get('code')
    state = request.args.get('state')

    # Verify state from request 
    if state != session.pop('csrf_state', None):
        return "State mismatch. Potential CSRF attack.", 400

    # Retrieve verifier from the session
    code_verifier = session.get('code_verifier', None)

    # Exchange auth code for an access token with tiktok
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    token_data = {
        'client_key': CLIENT_KEY,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI,
        'code_verifier': code_verifier
    }

    token_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Cache-Control': 'no-cache'
    }

    response = requests.post(token_url, data=token_data, headers=token_headers)
    
    if response.status_code == 200:
        token_response = response.json()
        open_id = token_response.get('open_id')
        save_token_data(token_response, open_id)
        # return f"Access token: {token_response.get('access_token')}<br>Refresh token: {token_response.get('refresh_token')}"
        return f"Retrieved Scoped Access Token Successfully."
    else:
        return f"Failed to obtain access token: {response.text}", 400
    
@app.route('/refresh_token/')
def refresh_token_route():
    """Route to manually refresh tokens (for testing and scheduled jobs)."""
    check_and_refresh_tokens()
    return "Token refresh process completed"

if __name__ == "__main__":
    app.run(debug=True, port=8000)