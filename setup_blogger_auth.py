"""
One-time Blogger OAuth2 Setup.
Run this once to authenticate with your Google account.
Saves a refresh token that the system uses automatically.

Usage: python setup_blogger_auth.py
"""

import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/blogger']
TOKEN_FILE = Path(__file__).parent / "data" / "blogger_token.json"
SA_FILE = Path(__file__).parent / "filejson" / "propane-fusion-441822-a5-5ad666121cae.json"


def create_oauth_client_config():
    """Create OAuth2 client config from Service Account's project."""
    # We need OAuth2 client credentials (not service account)
    # Let's create a desktop app flow
    print("=" * 60)
    print("BLOGGER OAUTH2 SETUP")
    print("=" * 60)
    print()
    print("Kamu perlu membuat OAuth2 Client ID di Google Cloud Console:")
    print()
    print("1. Buka: https://console.cloud.google.com/apis/credentials")
    print("   (Project: propane-fusion-441822-a5)")
    print()
    print("2. Klik '+ CREATE CREDENTIALS' → 'OAuth client ID'")
    print()
    print("3. Application type: 'Desktop app'")
    print("   Name: 'AI Money Machine'")
    print("   Klik 'Create'")
    print()
    print("4. Klik 'DOWNLOAD JSON' → simpan sebagai:")
    print(f"   {Path(__file__).parent / 'filejson' / 'oauth_client.json'}")
    print()
    print("5. Pastikan 'Blogger API v3' sudah di-enable:")
    print("   https://console.cloud.google.com/apis/library/blogger.googleapis.com")
    print()
    print("6. Jika diminta OAuth consent screen:")
    print("   - User Type: External")
    print("   - App name: AI Money Machine")
    print("   - Tambahkan email kamu sebagai Test User")
    print()
    print("Setelah file oauth_client.json tersimpan, jalankan script ini lagi.")
    print("=" * 60)


def authenticate():
    """Run OAuth2 flow to get and save refresh token."""
    client_file = Path(__file__).parent / "filejson" / "oauth_client.json"

    if not client_file.exists():
        create_oauth_client_config()
        return False

    # Check for existing token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            print("Token masih valid! Tidak perlu login ulang.")
            return True
        if creds and creds.expired and creds.refresh_token:
            print("Token expired, refreshing...")
            creds.refresh(Request())
            save_token(creds)
            print("Token refreshed!")
            return True

    # New authentication
    print("Opening browser for Google login...")
    print("(Login dengan akun Google yang memiliki blog di Blogger)")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=8090, open_browser=True)

    save_token(creds)
    print()
    print("Authentication berhasil! Token disimpan.")
    print(f"File: {TOKEN_FILE}")
    print()
    print("Sistem akan menggunakan token ini secara otomatis.")
    print("Kamu tidak perlu login lagi kecuali token di-revoke.")
    return True


def save_token(creds):
    """Save credentials to file."""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes or SCOPES,
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2, default=str)


if __name__ == "__main__":
    authenticate()
