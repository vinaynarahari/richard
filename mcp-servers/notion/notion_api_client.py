"""Notion client for the MCP server."""

import os
from typing import Any, Dict, List, Optional
try:
    from notion_client import Client as NotionClientLib
    from notion_client.errors import APIResponseError as APIError
except ImportError:
    # Fallback for older versions
    from notion_client import Client as NotionClientLib
    APIError = Exception


class NotionClient:
    """Notion client that provides database and page operations for MCP."""
    
    def __init__(self, auth_token: Optional[str] = None):
        """Initialize Notion client with auth token from environment or parameter."""
        # For now, use a placeholder since OAuth tokens are managed by orchestrator
        # In production, this would integrate with the existing OAuth flow
        self.auth_token = auth_token or os.getenv("NOTION_TOKEN") or "placeholder"
        try:
            self.client = NotionClientLib(auth=self.auth_token)
        except Exception:
            # For testing without real tokens
            self.client = None
    
    async def query_database(self, database_id: str, filter: Dict[str, Any] = None, sorts: List[Dict[str, Any]] = None, page_size: int = 10) -> Dict[str, Any]:
        """Query a Notion database."""
        if not self.client:
            raise ValueError("Notion client not initialized. Set NOTION_TOKEN environment variable.")
        try:
            kwargs = {
                "database_id": database_id,
                "page_size": page_size
            }
            
            if filter:
                kwargs["filter"] = filter
            
            if sorts:
                kwargs["sorts"] = sorts
            
            response = self.client.databases.query(**kwargs)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to query database: {str(e)}") from e
    
    async def create_page(self, database_id: str, properties: Dict[str, Any], children: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new page in a Notion database."""
        try:
            kwargs = {
                "parent": {"database_id": database_id},
                "properties": properties
            }
            
            if children:
                kwargs["children"] = children
            
            response = self.client.pages.create(**kwargs)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to create page: {str(e)}") from e
    
    async def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Update properties of a Notion page."""
        try:
            response = self.client.pages.update(
                page_id=page_id,
                properties=properties
            )
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to update page: {str(e)}") from e
    
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get details of a specific Notion page."""
        try:
            response = self.client.pages.retrieve(page_id=page_id)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to get page: {str(e)}") from e
    
    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """Get details of a specific Notion database."""
        try:
            response = self.client.databases.retrieve(database_id=database_id)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to get database: {str(e)}") from e
    
    async def search(self, query: str, filter: Dict[str, Any] = None, page_size: int = 10) -> Dict[str, Any]:
        """Search across Notion workspace."""
        try:
            kwargs = {
                "query": query,
                "page_size": page_size
            }
            
            if filter:
                kwargs["filter"] = filter
            
            response = self.client.search(**kwargs)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to search: {str(e)}") from e
    
    async def get_page_content(self, page_id: str) -> Dict[str, Any]:
        """Get the content blocks of a Notion page."""
        try:
            response = self.client.blocks.children.list(block_id=page_id)
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to get page content: {str(e)}") from e
    
    async def append_blocks(self, page_id: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Append blocks to a Notion page."""
        try:
            response = self.client.blocks.children.append(
                block_id=page_id,
                children=children
            )
            return response
        
        except APIError as e:
            raise RuntimeError(f"Failed to append blocks: {str(e)}") from e