from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
import os
import uuid
import json
from urllib.parse import urlencode
import httpx

# Keep oauth namespace for status; email endpoints live at root too for now
router = APIRouter(prefix="/oauth", tags=["oauth"])

# Public OAuth status + minimal Gmail OAuth flow (Authorization Code w/ existing token store)
@router.get("/status")
async def oauth_status() -> list[dict]:
    """
    Report whether Gmail OAuth is configured and list connected accounts (best-effort).
    """
    configured = bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_REDIRECT_URI"))
    return [{"provider": "google_gmail", "configured": configured}]

# Separate router for Gmail actions mounted in main.py under app root.
# Provide dev stubs under both /gmail/* and /dev/gmail/* to satisfy dispatcher fallbacks.
from fastapi import APIRouter as _APR

# Real Gmail integration
from ..services.gmail_service import GmailService, GmailTokenStore
from ..services.token_store import OAuthTokenStore
from ..memory.sqlite_store import SQLiteMemory

gmail_router = _APR(prefix="", tags=["gmail"])
_gmail = GmailService()
_token_store = GmailTokenStore(SQLiteMemory())
_contacts_memory = SQLiteMemory()

class GmailDraftRequest(BaseModel):
    account: Optional[str] = None
    to: List[str] = []
    subject: Optional[str] = ""
    body_markdown: Optional[str] = ""

def _require_account(req: GmailDraftRequest) -> str:
    if not req.account or not req.account.strip():
        raise HTTPException(status_code=400, detail="Missing sender account. Include 'account' (from email).")
    return req.account.strip()

# OAuth endpoints to connect a Gmail account (minimal, assumes you already obtained tokens client-side)
class GmailTokenUpsert(BaseModel):
    account: str
    token: dict  # full token payload including access_token/refresh_token/token_uri/client_id/client_secret/scopes

@router.post("/google/token/upsert")
async def google_token_upsert(payload: GmailTokenUpsert) -> dict:
    """
    Store or update OAuth token for a Gmail account in SQLite.
    This endpoint expects the token JSON already obtained (e.g., via a desktop loopback or web flow).
    """
    if not payload.account or not isinstance(payload.token, dict):
        raise HTTPException(status_code=400, detail="account and token are required")
    try:
        # Write via GmailTokenStore (backed by OAuthTokenStore)
        _id = await _token_store.save(payload.account, payload.token)
        # Also persist directly with OAuthTokenStore for clarity (no-op if same)
        OAuthTokenStore().save("google_gmail", payload.account, payload.token)
        return {"status": "ok", "id": _id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# New: Server-side code exchange helper (recommended)
class GmailCodeExchange(BaseModel):
    account: str  # sender email to bind the token to
    code: str     # authorization code from Google redirect

@router.post("/google/exchange")
async def google_exchange_code(payload: GmailCodeExchange) -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    scopes_env = os.getenv("GOOGLE_SCOPES") or ""
    scopes = scopes_env.split()
    if not client_id or not client_secret or not redirect_uri:
        raise HTTPException(status_code=400, detail="Missing GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REDIRECT_URI in env")

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": payload.code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    if resp.status_code != 200:
        try:
            err = resp.json()
        except Exception:
            err = {"text": resp.text}
        raise HTTPException(status_code=resp.status_code, detail={"provider": "google", "error": err})

    token = resp.json()
    # Normalize and persist
    token_dict = {
        "token": token.get("access_token"),
        "access_token": token.get("access_token"),
        "refresh_token": token.get("refresh_token"),
        "token_uri": token_url,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": scopes or token.get("scope", "").split(),
        "expires_in": token.get("expires_in"),
        "token_type": token.get("token_type"),
    }
    try:
        OAuthTokenStore().save("google_gmail", payload.account, token_dict)
        # Also keep the legacy adapter in sync
        await _token_store.save(payload.account, token_dict)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"status": "ok", "account": payload.account, "has_refresh": bool(token_dict.get("refresh_token"))}

# Helper to generate a Google OAuth consent URL (manual flow – exchange must be done client-side or via a separate callback)
@router.get("/google/authorize_url")
async def google_authorize_url() -> dict:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")
    # Accept scopes from env or fallback to a safe, full Gmail scope set if env is misconfigured.
    scopes_str = os.getenv("GOOGLE_SCOPES") or ""
    scopes = scopes_str.split()
    # Fallback if we somehow only have calendar or an empty value at runtime
    if not scopes or scopes == ["https://www.googleapis.com/auth/calendar"]:
        scopes = [
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.compose",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
        ]
    if not client_id or not redirect_uri or not scopes:
        raise HTTPException(status_code=400, detail="Missing GOOGLE_CLIENT_ID / GOOGLE_REDIRECT_URI / GOOGLE_SCOPES in env")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": " ".join(scopes),
        "include_granted_scopes": "true",
    }
    return {"authorize_url": f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"}

# Minimal callback to catch Google redirect and surface the authorization code to the user.
# Note: We are not exchanging the code server-side. Copy the code from the JSON response and
# call POST /oauth/google/token/upsert after exchanging it for tokens (or use your existing script).
# Support both /oauth/callback/google and legacy /callback/google (no /oauth prefix)
@router.get("/callback/google")
async def google_callback(code: Optional[str] = None, state: Optional[str] = None, scope: Optional[str] = None, error: Optional[str] = None) -> dict:
    if error:
        return {"status": "error", "error": error}
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' in callback.")
    return {"status": "ok", "code": code, "state": state, "scope": scope}

from fastapi import APIRouter as _APR2
legacy_router = _APR2(prefix="", tags=["oauth-legacy"])
@legacy_router.get("/callback/google")
async def google_callback_legacy(code: Optional[str] = None, state: Optional[str] = None, scope: Optional[str] = None, error: Optional[str] = None) -> dict:
    # Delegate to the /oauth/callback/google handler
    return await google_callback(code=code, state=state, scope=scope, error=error)
    if error:
        return {"status": "error", "error": error}
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' in callback.")
    # Just echo back the code and any received state/scope so the user can proceed to exchange it.
    return {"status": "ok", "code": code, "state": state, "scope": scope}

# Primary endpoints (use Gmail REST API through GmailService)
@gmail_router.post("/gmail/draft")
async def gmail_draft(req: GmailDraftRequest) -> dict:
    print("📧 /gmail/draft", {"account": req.account, "to": req.to, "subject": req.subject})
    account = _require_account(req)
    # Allow empty recipients/subject for drafts; coerce to safe defaults
    to = req.to or []
    subject = req.subject or ""
    body = req.body_markdown if req.body_markdown is not None else ""

    try:
        draft = await _gmail.create_draft(account=account, to=to, subject=subject, body_markdown=body)
        # Save contact memories for recipients
        try:
            for addr in to:
                _contacts_memory.insert(
                    kind="email_contact",
                    text=addr,
                    meta={"channel": "email", "address": addr},
                    vector=None,
                )
        except Exception:
            pass
        # Google returns {'id': 'draftId', 'message': {...}}; normalize id field
        draft_id = draft.get("id") or (draft.get("draft") or {}).get("id")
        return {"draft_id": draft_id or "unknown", "raw": draft}
    except Exception as e:
        print(f"[gmail.draft] error -> {e}")
        raise HTTPException(status_code=500, detail=str(e))

@gmail_router.post("/gmail/send")
async def gmail_send(req: GmailDraftRequest) -> dict:
    print("📨 /gmail/send", {"account": req.account, "to": req.to, "subject": req.subject})
    account = _require_account(req)
    if not req.to or not isinstance(req.to, list):
        raise HTTPException(status_code=400, detail="Missing recipients 'to'.")
    if not req.subject:
        raise HTTPException(status_code=400, detail="Missing 'subject'.")
    if req.body_markdown is None:
        raise HTTPException(status_code=400, detail="Missing 'body_markdown'.")

    try:
        sent = await _gmail.send_email(account=account, to=req.to, subject=req.subject, body_markdown=req.body_markdown)
        # Save contact memories for recipients
        try:
            for addr in req.to:
                _contacts_memory.insert(
                    kind="email_contact",
                    text=addr,
                    meta={"channel": "email", "address": addr},
                    vector=None,
                )
        except Exception:
            pass
        # Google returns {'id': 'msgId', 'threadId': '...', ...}
        msg_id = sent.get("id")
        return {"message_id": msg_id or "unknown", "raw": sent, "status": "sent" if msg_id else "unknown"}
    except Exception as e:
        print(f"[gmail.send] error -> {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Dev fallbacks now proxy to the real handlers for consistency
@gmail_router.post("/dev/gmail/draft")
async def dev_gmail_draft(req: GmailDraftRequest) -> dict:
    return await gmail_draft(req)

@gmail_router.post("/dev/gmail/send")
async def dev_gmail_send(req: GmailDraftRequest) -> dict:
    return await gmail_send(req)
