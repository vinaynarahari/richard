from __future__ import annotations

import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..memory.sqlite_store import SQLiteMemory
from .token_store import OAuthTokenStore


class GmailTokenStore:
    """
    Backward-compatible adapter that delegates to OAuthTokenStore(provider="google_gmail").
    """

    def __init__(self, memory: Optional[SQLiteMemory] = None, token_store: Optional[OAuthTokenStore] = None):
        self._store = token_store or OAuthTokenStore()

    async def load(self, account: str) -> Optional[Dict[str, Any]]:
        # Keep signature async for compatibility, but call sync store
        return self._store.load("google_gmail", account)

    async def save(self, account: str, token: Dict[str, Any]) -> str:
        self._store.save("google_gmail", account, token)
        return f"google_gmail:{account}"


class GmailService:
    """
    Gmail REST API client that:
      - loads/refreshes credentials from OAuthTokenStore-backed persistence
      - sends email and creates drafts with body_markdown
    """

    def __init__(self, token_store: Optional[GmailTokenStore] = None):
        self.token_store = token_store or GmailTokenStore()

    async def _build_creds(self, account: str) -> Credentials:
        token_dict = await self.token_store.load(account)
        if not token_dict:
            raise RuntimeError(f"No stored OAuth token for account {account}. Connect the account first.")

        missing = [k for k in ("token", "access_token", "refresh_token", "token_uri", "client_id", "client_secret", "scopes") if k not in token_dict]
        token_value = token_dict.get("token") or token_dict.get("access_token")
        if missing and not token_value:
            pass
        if not token_value:
            token_value = token_dict.get("access_token")
        if not token_value:
            raise RuntimeError(f"Invalid OAuth token for account {account} (no access token).")

        creds = Credentials(
            token=token_value,
            refresh_token=token_dict.get("refresh_token"),
            token_uri=token_dict.get("token_uri"),
            client_id=token_dict.get("client_id"),
            client_secret=token_dict.get("client_secret"),
            scopes=token_dict.get("scopes"),
        )
        return creds

    async def _maybe_persist_refreshed(self, account: str, creds: Credentials) -> None:
        try:
            # Credentials stores the new access token in creds.token and may update expiry
            token_dict = {
                "token": creds.token,
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes or []),
                "expiry": creds.expiry.isoformat() if getattr(creds, "expiry", None) else None,
            }
            await self.token_store.save(account, token_dict)
        except Exception:
            # Non-fatal if persistence fails
            pass

    @staticmethod
    def _mime_from_markdown(sender: str, to: List[str], subject: str, body_markdown: str) -> MIMEMultipart:
        msg = MIMEMultipart("alternative")
        msg["To"] = ", ".join(to)
        msg["From"] = sender
        msg["Subject"] = subject

        text_part = MIMEText(body_markdown, "plain", "utf-8")
        html_content = (
            "<br/>".join(body_markdown.splitlines())
            .replace("<", "<")
            .replace(">", ">")
        )
        html_part = MIMEText(f"<html><body><div>{html_content}</div></body></html>", "html", "utf-8")

        msg.attach(text_part)
        msg.attach(html_part)
        return msg

    @staticmethod
    def _encode_message(msg: MIMEMultipart) -> Dict[str, str]:
        raw_bytes = msg.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")
        return {"raw": raw_b64}

    async def send_email(self, account: str, to: List[str], subject: str, body_markdown: str) -> Dict[str, Any]:
        creds = await self._build_creds(account)
        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            mime = self._mime_from_markdown(account, to, subject, body_markdown)
            msg = self._encode_message(mime)
            sent = service.users().messages().send(userId="me", body=msg).execute()
            # Persist latest tokens (e.g., if refresh occurred)
            await self._maybe_persist_refreshed(account, creds)
            return sent
        except HttpError as e:
            try:
                err_json = e.error_details if hasattr(e, "error_details") else e.content
            except Exception:
                err_json = None
            raise RuntimeError(f"Gmail send failed: {e.status_code if hasattr(e, 'status_code') else 'unknown'} {err_json}") from e

    async def create_draft(self, account: str, to: List[str], subject: str, body_markdown: str) -> Dict[str, Any]:
        creds = await self._build_creds(account)
        try:
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            mime = self._mime_from_markdown(account, to, subject, body_markdown)
            msg = self._encode_message(mime)
            draft_body = {"message": msg}
            draft = service.users().drafts().create(userId="me", body=draft_body).execute()
            # Persist latest tokens
            await self._maybe_persist_refreshed(account, creds)
            return draft
        except HttpError as e:
            try:
                err_json = e.error_details if hasattr(e, "error_details") else e.content
            except Exception:
                err_json = None
            raise RuntimeError(f"Gmail draft failed: {e.status_code if hasattr(e, 'status_code') else 'unknown'} {err_json}") from e
