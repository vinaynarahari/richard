#!/usr/bin/env python3
"""Google Search MCP Server

An MCP server that provides Google Search API functionality including web search and image search.
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

from google_search_client import GoogleSearchClient

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("google-search-mcp-server")

class GoogleSearchMCPServer:
    def __init__(self):
        self.server = Server("google-search")
        self.search_client = GoogleSearchClient()
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                types.Tool(
                    name="google_web_search",
                    description="Search the web using Google Search API",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Starting index for results (for pagination)",
                                "default": 1,
                                "minimum": 1
                            },
                            "site_search": {
                                "type": "string",
                                "description": "Restrict search to a specific site (optional)"
                            },
                            "file_type": {
                                "type": "string",
                                "description": "Search for specific file types (e.g., 'pdf', 'doc')"
                            },
                            "date_restrict": {
                                "type": "string",
                                "description": "Restrict results by date (e.g., 'd1' for past day, 'w1' for past week, 'm1' for past month, 'y1' for past year)"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="google_image_search",
                    description="Search for images using Google Search API",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Image search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Starting index for results (for pagination)",
                                "default": 1,
                                "minimum": 1
                            },
                            "image_size": {
                                "type": "string",
                                "description": "Image size filter",
                                "enum": ["huge", "icon", "large", "medium", "small", "xlarge", "xxlarge"]
                            },
                            "image_type": {
                                "type": "string",
                                "description": "Image type filter",
                                "enum": ["clipart", "face", "lineart", "stock", "photo", "animated"]
                            },
                            "safe_search": {
                                "type": "string",
                                "description": "Safe search setting",
                                "enum": ["active", "off"],
                                "default": "active"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="google_news_search",
                    description="Search for news articles using Google Search API",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "News search query"
                            },
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            },
                            "start_index": {
                                "type": "integer",
                                "description": "Starting index for results (for pagination)",
                                "default": 1,
                                "minimum": 1
                            },
                            "date_restrict": {
                                "type": "string",
                                "description": "Restrict results by date (e.g., 'd1' for past day, 'w1' for past week, 'm1' for past month)"
                            },
                            "sort_by": {
                                "type": "string",
                                "description": "Sort order for results",
                                "enum": ["date", "relevance"],
                                "default": "relevance"
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
                if name == "google_web_search":
                    result = await self.search_client.web_search(
                        query=arguments["query"],
                        num_results=arguments.get("num_results", 10),
                        start_index=arguments.get("start_index", 1),
                        site_search=arguments.get("site_search"),
                        file_type=arguments.get("file_type"),
                        date_restrict=arguments.get("date_restrict")
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "google_image_search":
                    result = await self.search_client.image_search(
                        query=arguments["query"],
                        num_results=arguments.get("num_results", 10),
                        start_index=arguments.get("start_index", 1),
                        image_size=arguments.get("image_size"),
                        image_type=arguments.get("image_type"),
                        safe_search=arguments.get("safe_search", "active")
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "google_news_search":
                    result = await self.search_client.news_search(
                        query=arguments["query"],
                        num_results=arguments.get("num_results", 10),
                        start_index=arguments.get("start_index", 1),
                        date_restrict=arguments.get("date_restrict"),
                        sort_by=arguments.get("sort_by", "relevance")
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
                        server_name="google-search",
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
        server = GoogleSearchMCPServer()
        logger.info("Google Search MCP Server initialized successfully")
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
        server = GoogleSearchMCPServer()
        logger.info("Google Search MCP Server starting...")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)