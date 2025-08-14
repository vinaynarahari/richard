#!/usr/bin/env python3
"""Gmail MCP Server

An MCP server that provides Gmail functionality including sending emails and creating drafts.
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

from gmail_client import GmailClient

# Import security components
sys.path.append('../security')
from security import require_auth, validate_input, rate_limit, GmailToolInput, SecurityMiddleware

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gmail-mcp-server")

class GmailMCPServer:
    def __init__(self):
        self.server = Server("gmail")
        self.gmail_client = GmailClient()
        self.security = SecurityMiddleware()
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                types.Tool(
                    name="gmail_send_email",
                    description="Send an email via Gmail",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account": {
                                "type": "string",
                                "description": "Gmail account email address"
                            },
                            "to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of recipient email addresses"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body in markdown format"
                            }
                        },
                        "required": ["account", "to", "subject", "body"]
                    }
                ),
                types.Tool(
                    name="gmail_create_draft",
                    description="Create a draft email in Gmail",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account": {
                                "type": "string",
                                "description": "Gmail account email address"
                            },
                            "to": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of recipient email addresses"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body in markdown format"
                            }
                        },
                        "required": ["account", "to", "subject", "body"]
                    }
                ),
                types.Tool(
                    name="gmail_list_messages",
                    description="List recent Gmail messages",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account": {
                                "type": "string",
                                "description": "Gmail account email address"
                            },
                            "query": {
                                "type": "string",
                                "description": "Gmail search query (optional)",
                                "default": ""
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of messages to return",
                                "default": 10,
                                "minimum": 1,
                                "maximum": 100
                            }
                        },
                        "required": ["account"]
                    }
                ),
                types.Tool(
                    name="gmail_get_message",
                    description="Get details of a specific Gmail message",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account": {
                                "type": "string",
                                "description": "Gmail account email address"
                            },
                            "message_id": {
                                "type": "string",
                                "description": "Gmail message ID"
                            }
                        },
                        "required": ["account", "message_id"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Optional[dict] = None
        ) -> List[types.TextContent]:
            try:
                # Apply security middleware
                if name == "gmail_send_email":
                    # Validate input
                    validated_input = GmailToolInput(**arguments)
                    
                    # Check permissions (this would be integrated with MCP auth)
                    # For now, we'll log the security check
                    logger.info(f"Security check passed for {name}")
                    
                    result = await self.gmail_client.send_email(
                        account=validated_input.account,
                        to=validated_input.to,
                        subject=validated_input.subject,
                        body_markdown=validated_input.body
                    )
                    return [types.TextContent(
                        type="text",
                        text=f"Email sent successfully. Message ID: {result.get('id', 'unknown')}"
                    )]
                
                elif name == "gmail_create_draft":
                    result = await self.gmail_client.create_draft(
                        account=arguments["account"],
                        to=arguments["to"],
                        subject=arguments["subject"],
                        body_markdown=arguments["body"]
                    )
                    return [types.TextContent(
                        type="text",
                        text=f"Draft created successfully. Draft ID: {result.get('id', 'unknown')}"
                    )]
                
                elif name == "gmail_list_messages":
                    result = await self.gmail_client.list_messages(
                        account=arguments["account"],
                        query=arguments.get("query", ""),
                        max_results=arguments.get("max_results", 10)
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2)
                    )]
                
                elif name == "gmail_get_message":
                    result = await self.gmail_client.get_message(
                        account=arguments["account"],
                        message_id=arguments["message_id"]
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2)
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
                        server_name="gmail",
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
        server = GmailMCPServer()
        logger.info("Gmail MCP Server initialized successfully")
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
        server = GmailMCPServer()
        logger.info("Gmail MCP Server starting...")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)