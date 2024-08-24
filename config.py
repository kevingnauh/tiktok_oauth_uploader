import os

# OAuth 2.0 settings
CLIENT_KEY = os.getenv('TIKTOK_CLIENT_ID')
CLIENT_SECRET = os.getenv('TIKTOK_CLIENT_SECRET')
REDIRECT_URI = os.getenv('TIKTOK_REDIRECT_URI')

# Retry settings
MAX_RETRIES = 2

# Local token file used as storage - replace with database when needed
USER_TOKEN_FILENAME='user_tokens.json'