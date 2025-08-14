#!/usr/bin/env python3
import os, json, sys, urllib.request, urllib.error
from urllib.parse import urlencode

"""
Usage:
  1) Ensure env vars are set (GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI)
  2) Run with authorization codes (from the Google consent redirect) to exchange and upsert:
     python services/orchestrator/scripts/gmail_upsert.py \
       --account vinay.na.narahari@gmail.com --code "4/xxxx" \
       --account vinay.vv.narahari@gmail.com --code "4/yyyy"

  The script will:
    - POST to https://oauth2.googleapis.com/token to exchange each code for tokens
    - POST to http://127.0.0.1:5273/oauth/google/token/upsert to persist in SQLite
"""

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPSERT_URL = "http://127.0.0.1:5273/oauth/google/token/upsert"

def required_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        print(f"Missing required env: {name}", file=sys.stderr)
        sys.exit(1)
    return v

CLIENT_ID = required_env("GOOGLE_CLIENT_ID")
CLIENT_SECRET = required_env("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = required_env("GOOGLE_REDIRECT_URI")

def exchange_code(code: str) -> dict:
    data = urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode("utf-8")
    req = urllib.request.Request(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def upsert_token(account: str, token: dict) -> dict:
    payload = {
        "account": account,
        "token": {
            "access_token": token.get("access_token"),
            "refresh_token": token.get("refresh_token"),
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scopes": token.get("scope", "").split() if isinstance(token.get("scope"), str) else token.get("scope"),
            "expires_in": token.get("expires_in"),
            "id_token": token.get("id_token"),
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(UPSERT_URL, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode("utf-8"))

def parse_args(argv):
    # Supports repeated --account ... --code ... pairs
    pairs = []
    i = 0
    while i < len(argv):
        if argv[i] == "--account" and i + 1 < len(argv):
            account = argv[i + 1]
            i += 2
            if i < len(argv) and argv[i] == "--code" and i + 1 < len(argv):
                code = argv[i + 1]
                i += 2
                pairs.append((account, code))
            else:
                print("Expected --code after --account", file=sys.stderr)
                sys.exit(2)
        else:
            print(f"Unknown or misplaced arg: {argv[i]}", file=sys.stderr)
            sys.exit(2)
    if not pairs:
        print("Provide at least one --account EMAIL --code AUTH_CODE pair", file=sys.stderr)
        sys.exit(2)
    return pairs

def main():
    pairs = parse_args(sys.argv[1:])
    results = {}
    for account, code in pairs:
        try:
            token = exchange_code(code)
            upsert_resp = upsert_token(account, token)
            results[account] = {"status": "ok", "upsert": upsert_resp}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            results[account] = {"status": "error", "stage": "http", "code": e.code, "body": body}
        except Exception as e:
            results[account] = {"status": "error", "stage": "python", "error": str(e)}
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
