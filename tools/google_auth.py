"""Google OAuth for Drive + Gmail. First run opens a browser to consent; afterwards token.json is reused
and refreshed silently (needed for unattended weekly runs).

Usage (one-time): python tools/google_auth.py
"""
from __future__ import annotations

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from common import ROOT, get_logger

log = get_logger("gauth")
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",   # only files this app creates
    "https://www.googleapis.com/auth/gmail.send",   # send-only, cannot read mail
]
CREDS = ROOT / "credentials.json"
TOKEN = ROOT / "token.json"


def get_credentials(interactive: bool = True) -> Credentials:
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json())
            return creds
        except Exception as e:
            log.warning("Token refresh failed (%s) — re-consent needed", e)
    if not interactive:
        raise RuntimeError("Google token missing/expired. Run: .venv/Scripts/python tools/google_auth.py")
    if not CREDS.exists():
        raise RuntimeError("credentials.json not found in project root — see workflow Setup step 3.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    TOKEN.write_text(creds.to_json())
    log.info("Saved token.json")
    return creds


if __name__ == "__main__":
    get_credentials(interactive=True)
    print("Google auth OK")
