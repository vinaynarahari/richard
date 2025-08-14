#!/usr/bin/env python3
"""Notion MCP Server

An MCP server that provides Notion database operations including querying, creating, and updating pages.
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

from notion_api_client import NotionClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("notion-mcp-server")

class NotionMCPServer:
    def __init__(self):
        self.server = Server("notion")
        self.notion_client = NotionClient()
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                types.Tool(
                    name="notion_query_database",
                    description="Query a Notion database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Notion database ID"
                            },
                            "filter": {
                                "type": "object",
                                "description": "Filter criteria (optional)",
                                "default": {}
                            },
                            "sorts": {
                                "type": "array",
                                "description": "Sort criteria (optional)",
                                "default": []
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": ["database_id"]
                    }
                ),
                types.Tool(
                    name="notion_create_page",
                    description="Create a new page in a Notion database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Notion database ID"
                            },
                            "properties": {
                                "type": "object",
                                "description": "Page properties as key-value pairs"
                            },
                            "children": {
                                "type": "array",
                                "description": "Page content blocks (optional)",
                                "default": []
                            }
                        },
                        "required": ["database_id", "properties"]
                    }
                ),
                types.Tool(
                    name="notion_update_page",
                    description="Update properties of a Notion page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Notion page ID"
                            },
                            "properties": {
                                "type": "object",
                                "description": "Properties to update as key-value pairs"
                            }
                        },
                        "required": ["page_id", "properties"]
                    }
                ),
                types.Tool(
                    name="notion_get_page",
                    description="Get details of a specific Notion page",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Notion page ID"
                            }
                        },
                        "required": ["page_id"]
                    }
                ),
                types.Tool(
                    name="notion_get_database",
                    description="Get details of a specific Notion database",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Notion database ID"
                            }
                        },
                        "required": ["database_id"]
                    }
                ),
                types.Tool(
                    name="notion_search",
                    description="Search across Notion workspace",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "filter": {
                                "type": "object",
                                "description": "Filter criteria (optional)",
                                "default": {}
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": ["query"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Optional[dict] = None
        ) -> List[types.TextContent]:
            try:
                if name == "notion_query_database":
                    result = await self.notion_client.query_database(
                        database_id=arguments["database_id"],
                        filter=arguments.get("filter", {}),
                        sorts=arguments.get("sorts", []),
                        page_size=arguments.get("page_size", 10)
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "notion_create_page":
                    result = await self.notion_client.create_page(
                        database_id=arguments["database_id"],
                        properties=arguments["properties"],
                        children=arguments.get("children", [])
                    )
                    return [types.TextContent(
                        type="text",
                        text=f"Page created successfully. Page ID: {result.get('id', 'unknown')}"
                    )]
                
                elif name == "notion_update_page":
                    result = await self.notion_client.update_page(
                        page_id=arguments["page_id"],
                        properties=arguments["properties"]
                    )
                    return [types.TextContent(
                        type="text",
                        text=f"Page updated successfully. Page ID: {result.get('id', 'unknown')}"
                    )]
                
                elif name == "notion_get_page":
                    result = await self.notion_client.get_page(
                        page_id=arguments["page_id"]
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "notion_get_database":
                    result = await self.notion_client.get_database(
                        database_id=arguments["database_id"]
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "notion_search":
                    result = await self.notion_client.search(
                        query=arguments["query"],
                        filter=arguments.get("filter", {}),
                        page_size=arguments.get("page_size", 10)
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                else:
                    raise ValueError(f"Unknown tool: {name}")
            
            except Exception as e:
                logger.error(f"Error calling tool {name}: {e}")
                return [types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]

    async def run(self):
        """Run the MCP server."""
        try:
            async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name="notion",
                        server_version="0.1.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    ),
                )
        except Exception as e:
            logger.error(f"Server error: {e}")
            # For testing, we'll catch and log errors rather than crash


async def health_check():
    """Simple health check for testing."""
    try:
        server = NotionMCPServer()
        logger.info("Notion MCP Server initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False

if __name__ == "__main__":
    # Check for health check argument
    if len(sys.argv) > 1 and sys.argv[1] == "--health":
        success = asyncio.run(health_check())
        sys.exit(0 if success else 1)
    
    try:
        server = NotionMCPServer()
        logger.info("Notion MCP Server starting...")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)