#!/usr/bin/env python3
"""
Web Researcher MCP Server - Combines search with content fetching to answer questions.
Searches the web, fetches relevant content, and processes it to provide complete answers.
"""

import asyncio
import json
import logging
import sys
import os
from typing import Any, Dict, List, Optional, Sequence
import aiohttp
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types

# Add security module to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'security'))

try:
    from middleware import SecurityMiddleware, require_auth, validate_input, rate_limit
    from validation import BrowserToolInput
except ImportError as e:
    print(f"Warning: Security modules not available: {e}")
    
    # Define no-op decorators for testing
    def require_auth(permission):
        def decorator(func):
            return func
        return decorator
    
    def validate_input(model):
        def decorator(func):
            return func
        return decorator
    
    def rate_limit(key_func):
        def decorator(func):
            return func
        return decorator

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("web-researcher-mcp-server")

class WebResearcher:
    """Web researcher that searches and fetches content to answer questions."""
    
    def __init__(self):
        self.session = None
        self.max_content_length = 50000  # Limit content size
        self.timeout = 30  # Request timeout
        
    async def setup_session(self):
        """Initialize HTTP session."""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
            )
    
    async def close_session(self):
        """Close HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def search_web(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search the web using DuckDuckGo (fallback implementation)."""
        try:
            await self.setup_session()
            
            # Use DuckDuckGo instant answer API
            search_url = "https://api.duckduckgo.com/"
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            async with self.session.get(search_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []
                    
                    # Extract related topics as search results
                    for topic in data.get('RelatedTopics', [])[:max_results]:
                        if isinstance(topic, dict) and 'FirstURL' in topic:
                            results.append({
                                'title': topic.get('Text', '').split(' - ')[0] if ' - ' in topic.get('Text', '') else topic.get('Text', ''),
                                'url': topic.get('FirstURL', ''),
                                'snippet': topic.get('Text', '')
                            })
                    
                    # If no related topics, try to use the abstract
                    if not results and data.get('Abstract'):
                        results.append({
                            'title': data.get('Heading', query),
                            'url': data.get('AbstractURL', ''),
                            'snippet': data.get('Abstract', '')
                        })
                    
                    return results
                    
        except Exception as e:
            logger.error(f"Search failed: {e}")
            
        # Fallback: return some common financial sites for stock queries
        if 'stock' in query.lower() or 'price' in query.lower():
            return [
                {
                    'title': 'Google Finance',
                    'url': 'https://www.google.com/finance/',
                    'snippet': 'Real-time stock quotes and financial information'
                },
                {
                    'title': 'Yahoo Finance',
                    'url': 'https://finance.yahoo.com/',
                    'snippet': 'Stock market data and financial news'
                },
                {
                    'title': 'MarketWatch',
                    'url': 'https://www.marketwatch.com/',
                    'snippet': 'Financial market news and analysis'
                }
            ]
        
        return []
    
    async def fetch_content(self, url: str) -> Optional[str]:
        """Fetch and extract text content from a web page."""
        try:
            await self.setup_session()
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    content = await response.read()
                    
                    # Limit content size
                    if len(content) > self.max_content_length:
                        content = content[:self.max_content_length]
                    
                    # Parse HTML and extract text
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style"]):
                        script.decompose()
                    
                    # Extract text
                    text = soup.get_text()
                    
                    # Clean up whitespace
                    lines = (line.strip() for line in text.splitlines())
                    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                    text = ' '.join(chunk for chunk in chunks if chunk)
                    
                    return text[:self.max_content_length] if text else None
                    
        except Exception as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            
        return None
    
    async def research_question(self, question: str, max_sources: int = 3) -> Dict[str, Any]:
        """Research a question by searching and fetching content from multiple sources."""
        try:
            # Search for relevant pages
            search_results = await self.search_web(question, max_sources * 2)
            
            if not search_results:
                return {
                    'question': question,
                    'answer': 'No search results found for this question.',
                    'sources': [],
                    'status': 'no_results'
                }
            
            # Fetch content from top results
            sources = []
            fetched_content = []
            
            for result in search_results[:max_sources]:
                if result.get('url'):
                    content = await self.fetch_content(result['url'])
                    if content:
                        sources.append({
                            'title': result.get('title', ''),
                            'url': result.get('url', ''),
                            'snippet': result.get('snippet', '')
                        })
                        fetched_content.append(content)
            
            if not fetched_content:
                return {
                    'question': question,
                    'answer': 'Could not fetch content from search results.',
                    'sources': sources,
                    'status': 'fetch_failed'
                }
            
            # Combine and summarize content to answer the question
            combined_content = '\n\n'.join(fetched_content)
            answer = self._extract_answer(question, combined_content)
            
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'content_length': len(combined_content),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Research failed: {e}")
            return {
                'question': question,
                'answer': f'Research failed: {str(e)}',
                'sources': [],
                'status': 'error'
            }
    
    def _extract_answer(self, question: str, content: str) -> str:
        """Extract relevant information from content to answer the question."""
        # Simple keyword-based extraction for stock prices
        if 'stock price' in question.lower() or 'current price' in question.lower():
            # Look for price patterns in the content
            price_patterns = [
                r'\$[\d,]+\.?\d*',  # $123.45 or $1,234
                r'[\d,]+\.?\d*\s*(?:USD|dollars?)',  # 123.45 USD
                r'Price:?\s*\$?[\d,]+\.?\d*',  # Price: $123.45
                r'[\d,]+\.?\d*\s*per share'  # 123.45 per share
            ]
            
            found_prices = []
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                found_prices.extend(matches)
            
            if found_prices:
                # Get unique prices and format response
                unique_prices = list(set(found_prices[:3]))  # Limit to 3 prices
                return f"Based on the search results, here are current price indicators: {', '.join(unique_prices)}. Please note that stock prices change frequently and you should verify current prices from official financial sources."
        
        # For other questions, return a summary of the first few sentences
        sentences = content.split('.')[:5]  # First 5 sentences
        clean_sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 10]
        
        if clean_sentences:
            summary = '. '.join(clean_sentences[:3]) + '.'
            return f"Based on the search results: {summary}"
        
        return "I found some information but couldn't extract a clear answer to your question. Please check the source links for more details."

class WebResearcherMCPServer:
    def __init__(self):
        self.server = Server("web-researcher")
        self.researcher = WebResearcher()
        self._setup_handlers()
    
    def _setup_handlers(self):
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            return [
                types.Tool(
                    name="research_question",
                    description="Research a question by searching the web and fetching content from relevant sources to provide a comprehensive answer",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to research"
                            },
                            "max_sources": {
                                "type": "integer",
                                "description": "Maximum number of sources to fetch content from",
                                "default": 3,
                                "minimum": 1,
                                "maximum": 5
                            }
                        },
                        "required": ["question"]
                    }
                ),
                types.Tool(
                    name="fetch_page_content",
                    description="Fetch and extract text content from a specific web page URL",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "The URL to fetch content from"
                            }
                        },
                        "required": ["url"]
                    }
                )
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Optional[dict] = None
        ) -> List[types.TextContent]:
            try:
                if name == "research_question":
                    result = await self.researcher.research_question(
                        question=arguments["question"],
                        max_sources=arguments.get("max_sources", 3)
                    )
                    return [types.TextContent(
                        type="text",
                        text=json.dumps(result, indent=2, default=str)
                    )]
                
                elif name == "fetch_page_content":
                    content = await self.researcher.fetch_content(arguments["url"])
                    result = {
                        "url": arguments["url"],
                        "content": content,
                        "status": "success" if content else "failed"
                    }
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
                        server_name="web-researcher",
                        server_version="0.1.0",
                        capabilities=self.server.get_capabilities(
                            notification_options=NotificationOptions(),
                            experimental_capabilities={},
                        ),
                    ),
                )
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            await self.researcher.close_session()

if __name__ == "__main__":
    try:
        server = WebResearcherMCPServer()
        logger.info("Web Researcher MCP Server starting...")
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)