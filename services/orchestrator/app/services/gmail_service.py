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


class GmailTokenStore:
    """
    Persist OAuth tokens in SQLiteMemory (existing DB).
    We store one row per (provider, account), where:
      - provider: "google_gmail"
      - key: account email (e.g., "me@example.com")
      - text: JSON of token dict {access_token, refresh_token, token_uri, client_id, client_secret, scopes, expiry, ...}
    """

    def __init__(self, memory: Optional[SQLiteMemory] = None):
        self.memory = memory or SQLiteMemory()

    async def load(self, account: str) -> Optional[Dict[str, Any]]:
        # Reuse memory search to find an exact match for this account
        try:
            # We store with kind="oauth_token" and provider in meta
            results = await self.memory.search(account, top_k=20)
        except Exception:
            return None
        # Find the newest record matching provider=google_gmail and key == account
        for item, _score in results:
            try:
                if item.kind == "oauth_token" and item.meta and item.meta.get("provider") == "google_gmail":
                    if (item.meta.get("account") or "").lower() == account.lower():
                        # item.text holds the token json
                        return json.loads(item.text)
            except Exception:
                continue
        return None

    async def save(self, account: str, token: Dict[str, Any]) -> str:
        # Insert a new record (upsert semantics could be added later)
        return await self.memory.insert_with_embedding(
            kind="oauth_token",
            text=json.dumps(token),
            meta={"provider": "google_gmail", "account": account},
        )


class GmailService:
    """
    Gmail REST API client that:
      - loads/refreshes credentials from SQLite-backed store
      - sends email and creates drafts with body_markdown
    """

    def __init__(self, token_store: Optional[GmailTokenStore] = None):
        self.token_store = token_store or GmailTokenStore()

    async def _build_creds(self, account: str) -> Credentials:
        token_dict = await self.token_store.load(account)
        if not token_dict:
            raise RuntimeError(f"No stored OAuth token for account {account}. Connect the account first.")

        # google.oauth2.credentials.Credentials expects standard fields
        # Ensure required fields exist in token_dict (access_token/refresh_token/token_uri/client_id/client_secret/scopes)
        missing = [k for k in ("token", "access_token", "refresh_token", "token_uri", "client_id", "client_secret", "scopes") if k not in token_dict]
        # Some implementations store access token as "access_token" not "token"
        token_value = token_dict.get("token") or token_dict.get("access_token")
        if missing and not token_value:
            # Allow missing "token" if "access_token" provided
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

    @staticmethod
    def _mime_from_markdown(sender: str, to: List[str], subject: str, body_markdown: str) -> MIMEMultipart:
        # Compose multipart/alternative with plain text and html (basic conversion)
        msg = MIMEMultipart("alternative")
        msg["To"] = ", ".join(to)
        msg["From"] = sender
        msg["Subject"] = subject

        # Naive markdown to HTML fallback (could integrate a real md renderer later)
        # Escape basic content; keep it simple
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
            return sent  # contains id, threadId, labelIds...
        except HttpError as e:
            # Surface Gmail error details
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
            return draft  # contains id and message with id
        except HttpError as e:
            try:
                err_json = e.error_details if hasattr(e, "error_details") else e.content
            except Exception:
                err_json = None
            raise RuntimeError(f"Gmail draft failed: {e.status_code if hasattr(e, 'status_code') else 'unknown'} {err_json}") from e
