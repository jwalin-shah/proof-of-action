"""One-time Gmail OAuth onboarding for self-hosted Proof-of-Action.

    $ python scripts/onboard.py

Opens a browser, you grant Gmail read access, the refresh token lands at
~/.config/proof-of-action/gmail-token.json. The token never leaves your
machine. The agent reads it locally.

Requires credentials.json (the installed-app OAuth client) in the repo root.
Copy credentials.example.json and fill in your own GCP values, or use the one
shipped with the repo (shared client — only identifies the app, not you).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
REPO = Path(__file__).resolve().parent.parent
CREDS_FILE = REPO / "credentials.json"
TOKEN_DIR = Path.home() / ".config" / "proof-of-action"
TOKEN_FILE = TOKEN_DIR / "gmail-token.json"


def main() -> int:
    if not CREDS_FILE.exists():
        print(f"error: {CREDS_FILE} not found.")
        print("       Copy credentials.example.json and fill in your GCP")
        print("       OAuth client values (or use the shipped one).")
        return 1

    TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    print("Proof-of-Action — Gmail OAuth onboarding")
    print("─" * 60)
    print(f"OAuth client: {CREDS_FILE}")
    print(f"Token will land at: {TOKEN_FILE}")
    print(f"Scope requested: {SCOPES[0]} (read-only)")
    print()
    print("A browser window will open. Grant access to your Gmail,")
    print("then return here. Your refresh token stays on this machine.")
    print("─" * 60)

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    TOKEN_FILE.write_text(creds.to_json())
    TOKEN_FILE.chmod(0o600)

    parsed = json.loads(creds.to_json())
    print()
    print(f"✓ Token saved for account: {parsed.get('account', '(unknown)')}")
    print(f"  File: {TOKEN_FILE}")
    print()
    print("Next: POA_SOURCE=gmail ./scripts/demo.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
