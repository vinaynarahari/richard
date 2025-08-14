"""Gmail client wrapper for the MCP server."""

import sys
import os
from typing import Any, Dict, List, Optional

# Add the services/orchestrator path to Python path so we can import existing services
sys.path.append(os.path.join(os.path.dirname(__file__), '../../services/orchestrator'))

from app.services.gmail_service import GmailService, GmailTokenStore


class GmailClient:
    """Gmail client that wraps the existing GmailService for MCP."""
    
    def __init__(self):
        self.gmail_service = GmailService()
    
    async def send_email(self, account: str, to: List[str], subject: str, body_markdown: str) -> Dict[str, Any]:
        """Send an email via Gmail."""
        return await self.gmail_service.send_email(account, to, subject, body_markdown)
    
    async def create_draft(self, account: str, to: List[str], subject: str, body_markdown: str) -> Dict[str, Any]:
        """Create a draft email in Gmail."""
        return await self.gmail_service.create_draft(account, to, subject, body_markdown)
    
    async def list_messages(self, account: str, query: str = "", max_results: int = 10) -> Dict[str, Any]:
        """List recent Gmail messages."""
        # Build credentials
        creds = await self.gmail_service._build_creds(account)
        
        try:
            from googleapiclient.discovery import build
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            
            # List messages
            results = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get("messages", [])
            
            # Get basic info for each message
            message_list = []
            for msg in messages:
                msg_detail = service.users().messages().get(
                    userId="me",
                    id=msg["id"],
                    format="metadata",
                    metadataHeaders=["From", "To", "Subject", "Date"]
                ).execute()
                
                headers = {h["name"]: h["value"] for h in msg_detail.get("payload", {}).get("headers", [])}
                message_list.append({
                    "id": msg_detail["id"],
                    "threadId": msg_detail["threadId"],
                    "from": headers.get("From", ""),
                    "to": headers.get("To", ""),
                    "subject": headers.get("Subject", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg_detail.get("snippet", "")
                })
            
            # Persist latest tokens
            await self.gmail_service._maybe_persist_refreshed(account, creds)
            
            return {
                "messages": message_list,
                "resultSizeEstimate": results.get("resultSizeEstimate", 0)
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to list messages: {str(e)}") from e
    
    async def get_message(self, account: str, message_id: str) -> Dict[str, Any]:
        """Get details of a specific Gmail message."""
        # Build credentials
        creds = await self.gmail_service._build_creds(account)
        
        try:
            from googleapiclient.discovery import build
            service = build("gmail", "v1", credentials=creds, cache_discovery=False)
            
            # Get message details
            message = service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()
            
            # Extract headers
            headers = {h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])}
            
            # Extract body
            body = self._extract_message_body(message.get("payload", {}))
            
            # Persist latest tokens
            await self.gmail_service._maybe_persist_refreshed(account, creds)
            
            return {
                "id": message["id"],
                "threadId": message["threadId"],
                "labelIds": message.get("labelIds", []),
                "snippet": message.get("snippet", ""),
                "historyId": message.get("historyId"),
                "internalDate": message.get("internalDate"),
                "headers": headers,
                "body": body
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to get message: {str(e)}") from e
    
    def _extract_message_body(self, payload: Dict[str, Any]) -> str:
        """Extract the body text from a Gmail message payload."""
        body = ""
        
        if "body" in payload and payload["body"].get("data"):
            import base64
            body_data = payload["body"]["data"]
            body = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
        
        elif "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                    import base64
                    body_data = part["body"]["data"]
                    body = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
                    break
        
        return body