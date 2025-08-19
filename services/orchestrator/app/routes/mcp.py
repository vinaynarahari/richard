#!/usr/bin/env python3
"""
MCP Routes - Provide HTTP endpoints for MCP server tools
"""

import asyncio
import json
import logging
import sys
import os
import subprocess
from typing import Any, Dict, List, Optional
import aiohttp
from bs4 import BeautifulSoup
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])

class ResearchRequest(BaseModel):
    question: str
    max_sources: int = 3

class ResearchResponse(BaseModel):
    question: str
    answer: str
    sources: List[Dict[str, str]]
    content_length: Optional[int] = None
    status: str

class SendMessageRequest(BaseModel):
    recipient: str
    message: str

class SendMessageResponse(BaseModel):
    status: str
    message: str
    recipient: str

class GetMessagesRequest(BaseModel):
    hours: int = 24
    contact: Optional[str] = None

class GetMessagesResponse(BaseModel):
    messages: List[Dict[str, Any]]
    count: int
    status: str

class ContactSearchRequest(BaseModel):
    query: str
    max_results: int = 5

class ContactSearchResponse(BaseModel):
    contacts: List[Dict[str, Any]]
    count: int
    status: str

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
        """Search the web using DuckDuckGo."""
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
        if any(term in query.lower() for term in ['stock', 'price', 'market', 'finance']):
            return [
                {
                    'title': 'MarketWatch',
                    'url': 'https://www.marketwatch.com/',
                    'snippet': 'Financial market news and analysis'
                },
                {
                    'title': 'Yahoo Finance',
                    'url': 'https://finance.yahoo.com/',
                    'snippet': 'Stock market data and financial news'
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
                    'answer': f"I couldn't find search results for '{question}'. This might be a very specific query or the search service may be temporarily unavailable.",
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
                # If we have search results but couldn't fetch content, still provide the snippets
                if search_results:
                    answer = "Based on search results: " + '; '.join([
                        result.get('snippet', '') for result in search_results[:2] 
                        if result.get('snippet')
                    ])
                    return {
                        'question': question,
                        'answer': answer,
                        'sources': [{'title': r.get('title', ''), 'url': r.get('url', ''), 'snippet': r.get('snippet', '')} for r in search_results[:max_sources]],
                        'status': 'partial_success'
                    }
                
                return {
                    'question': question,
                    'answer': 'Could not fetch detailed content from search results, but found some relevant sources.',
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
                'answer': f'I encountered an error while researching: {str(e)}. Please try rephrasing your question.',
                'sources': [],
                'status': 'error'
            }
    
    def _extract_answer(self, question: str, content: str) -> str:
        """Extract relevant information from content to answer the question."""
        # Universal answer extraction - works for any topic
        question_lower = question.lower()
        
        # Split content into sentences for analysis
        sentences = content.split('.')
        clean_sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 15]
        
        if not clean_sentences:
            return "I found some information but couldn't extract a clear answer."
        
        # Extract keywords from question
        question_keywords = set(re.findall(r'\b[a-z]{3,}\b', question_lower))
        stop_words = {'what', 'when', 'who', 'where', 'how', 'why', 'which', 'the', 'was', 'were', 'are', 'and', 'but', 'for'}
        question_keywords = question_keywords - stop_words
        
        # Score sentences based on keyword relevance
        scored_sentences = []
        for sentence in clean_sentences[:15]:  # Limit to first 15 sentences
            sentence_words = set(re.findall(r'\b[a-z]{3,}\b', sentence.lower()))
            keyword_matches = len(question_keywords.intersection(sentence_words))
            
            # Bonus for informative patterns
            info_bonus = 0
            if re.search(r'\b(?:is|was|are|were)\s+(?:a|an|the)\b', sentence, re.IGNORECASE):
                info_bonus += 1
            if re.search(r'\b(?:founded|created|invented|discovered|known|located)\b', sentence, re.IGNORECASE):
                info_bonus += 1
            if re.search(r'\b\d+\b', sentence):  # Contains numbers
                info_bonus += 1
                
            total_score = keyword_matches * 2 + info_bonus
            if total_score > 0:
                scored_sentences.append((total_score, sentence))
        
        # Get best sentences
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        
        if scored_sentences:
            # Return top 1-2 most relevant sentences
            best_sentences = [s[1] for s in scored_sentences[:2] if s[0] > 0]
            if best_sentences:
                answer = '. '.join(best_sentences).rstrip('.') + '.'
                return f"Based on the search results: {answer}"
        
        # Fallback: return first substantial sentence
        for sentence in clean_sentences[:5]:
            if len(sentence) > 25 and not any(junk in sentence.lower() for junk in ['cookie', 'privacy', 'subscribe', 'follow']):
                return f"According to the sources: {sentence.rstrip('.')}."
        
        return "I found some information but couldn't extract a specific answer to your question."

class iMCPClient:
    """Client for iMCP server to access contacts and messages."""
    
    def __init__(self):
        self.mcp_process = None
        self.request_id = 0
        self.initialized = False
    
    async def _get_next_id(self) -> int:
        """Get next request ID."""
        self.request_id += 1
        return self.request_id
    
    async def _ensure_mcp_process(self):
        """Ensure iMCP process is running and initialized."""
        if self.mcp_process is None or self.mcp_process.poll() is not None:
            try:
                # Start the iMCP server process
                self.mcp_process = subprocess.Popen(
                    ["/Applications/iMCP.app/Contents/MacOS/imcp-server"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0
                )
                
                # Initialize the MCP connection
                if not self.initialized:
                    init_request = {
                        "jsonrpc": "2.0",
                        "id": await self._get_next_id(),
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "roots": {
                                    "listChanged": True
                                },
                                "sampling": {}
                            },
                            "clientInfo": {
                                "name": "richard-orchestrator",
                                "version": "1.0.0"
                            }
                        }
                    }
                    
                    # Send initialization
                    request_line = json.dumps(init_request) + "\n"
                    self.mcp_process.stdin.write(request_line)
                    self.mcp_process.stdin.flush()
                    
                    # Wait for response
                    await asyncio.sleep(1)
                    self.initialized = True
                    
            except Exception as e:
                logger.error(f"Failed to start iMCP process: {e}")
                raise
    
    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the iMCP server."""
        try:
            await self._ensure_mcp_process()
            
            request = {
                "jsonrpc": "2.0",
                "id": await self._get_next_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            # Log the request for debugging
            logger.info(f"Sending iMCP request: {json.dumps(request)}")
            
            # Send the request
            request_line = json.dumps(request) + "\n"
            self.mcp_process.stdin.write(request_line)
            self.mcp_process.stdin.flush()
            
            # Read response
            try:
                await asyncio.sleep(2)
                response_line = self.mcp_process.stdout.readline()
                if response_line:
                    logger.info(f"iMCP response: {response_line.strip()}")
                    response = json.loads(response_line.strip())
                    if "result" in response:
                        return {"status": "success", "data": response["result"]}
                    elif "error" in response:
                        logger.error(f"iMCP tool error: {response['error']}")
                        return {"status": "error", "message": str(response["error"])}
                
                return {"status": "error", "message": "No response from iMCP server"}
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse iMCP response: {e}")
                return {"status": "error", "message": "Invalid response from iMCP server"}
                
        except Exception as e:
            logger.error(f"iMCP tool call failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def search_contacts(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        """Search contacts using enhanced direct access with fuzzy matching."""
        try:
            # Use the enhanced direct contact search
            from mac_messages_mcp.messages import find_contact_by_name
            
            import asyncio
            import concurrent.futures
            
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                contacts_result = await loop.run_in_executor(
                    executor, 
                    find_contact_by_name, 
                    query,
                    max_results
                )
            
            logger.info(f"Enhanced contact search result: Found {len(contacts_result)} matches")
            
            # Convert to our expected format
            contacts = []
            for contact in contacts_result:
                contacts.append({
                    'name': contact['name'],
                    'phone_numbers': [contact['phone']] if contact.get('phone') else [],
                    'emails': [],  # Could be enhanced to include emails if available
                    'primary_phone': contact.get('phone'),
                    'confidence': contact.get('confidence', 'unknown'),
                    'match_type': contact.get('match_type', 'fuzzy'),
                    'score': contact.get('score', 0.0)
                })
            
            return {
                'contacts': contacts,
                'count': len(contacts),
                'status': 'success',
                'search_type': 'enhanced_fuzzy_matching'
            }
            
        except Exception as e:
            logger.error(f"Failed to search contacts with enhanced method: {e}")
            # Fallback to original iMCP method
            try:
                result = await self._call_mcp_tool("searchContacts", {
                    "query": query,
                    "limit": max_results
                })
                
                if result.get('status') == 'error':
                    return {
                        'contacts': [],
                        'count': 0,
                        'status': 'error'
                    }
                
                # Parse the JSON-LD response from iMCP
                contacts_data = result.get('data', [])
                contacts = []
                
                if isinstance(contacts_data, list):
                    for contact in contacts_data[:max_results]:
                        # Extract contact info from JSON-LD format
                        name = contact.get('name', 'Unknown')
                        phone_numbers = []
                        emails = []
                        
                        # iMCP returns structured contact data
                        if 'telephone' in contact:
                            phone_numbers = [contact['telephone']] if isinstance(contact['telephone'], str) else contact['telephone']
                        if 'email' in contact:
                            emails = [contact['email']] if isinstance(contact['email'], str) else contact['email']
                        
                        contacts.append({
                            'name': name,
                            'phone_numbers': phone_numbers,
                            'emails': emails,
                            'primary_phone': phone_numbers[0] if phone_numbers else None
                        })
                
                return {
                    'contacts': contacts,
                    'count': len(contacts),
                    'status': 'success',
                    'search_type': 'imcp_fallback'
                }
                
            except Exception as fallback_e:
                logger.error(f"Both enhanced and fallback contact search failed: {fallback_e}")
                return {
                    'contacts': [],
                    'count': 0,
                    'status': 'error'
                }
    
    async def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        """Send message through iMCP (if available) or fallback to direct."""
        # For now, we'll delegate to the direct client since iMCP might not have send capability
        # But we could potentially use iMCP for contact resolution
        return await _direct_message_client.send_message(recipient, message)
    
    async def get_recent_messages(self, hours: int = 24, contact: Optional[str] = None) -> Dict[str, Any]:
        """Get recent messages through iMCP."""
        try:
            result = await self._call_mcp_tool("fetchMessageHistory", {
                "participants": [contact] if contact else [],
                "timeRange": f"last {hours} hours"
            })
            
            if result.get('status') == 'error':
                return {
                    'messages': [],
                    'count': 0,
                    'status': 'error'
                }
            
            # Parse messages from iMCP response
            messages_data = result.get('data', [])
            messages = []
            
            if isinstance(messages_data, list):
                for msg in messages_data:
                    messages.append({
                        'sender': msg.get('sender', 'Unknown'),
                        'message': msg.get('text', ''),
                        'timestamp': msg.get('dateCreated', ''),
                        'is_from_me': msg.get('sender') == 'me'
                    })
            
            return {
                'messages': messages,
                'count': len(messages),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Failed to get messages from iMCP: {e}")
            return {
                'messages': [],
                'count': 0,
                'status': 'error'
            }
    
    def cleanup(self):
        """Clean up iMCP process."""
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                self.mcp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
            except Exception:
                pass

class DirectMessageClient:
    """Direct client for mac-messages functionality, bypassing MCP protocol issues."""
    
    def __init__(self):
        self.mac_messages_path = "/Users/vinaynarahari/Desktop/Github/richard/mac_messages_mcp"
        self._setup_path()
    
    def _setup_path(self):
        """Add mac_messages_mcp to Python path."""
        import sys
        if self.mac_messages_path not in sys.path:
            sys.path.insert(0, self.mac_messages_path)
    
    async def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        """Send a message directly using the enhanced mac_messages_mcp library with fuzzy contact matching."""
        try:
            # Import the enhanced function directly
            from mac_messages_mcp.messages import send_message
            
            # Call the enhanced function directly in a thread to avoid blocking
            import asyncio
            import concurrent.futures
            
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor, 
                    send_message, 
                    recipient, 
                    message
                )
            
            logger.info(f"Enhanced message send result: {result}")
            
            # Check if result indicates multiple matches or contact selection needed
            if "contact:" in result and "Found" in result:
                return {
                    'status': 'multiple_matches',
                    'message': result,
                    'recipient': recipient,
                    'action_required': 'contact_selection'
                }
            elif "successfully" in result.lower():
                return {
                    'status': 'success',
                    'message': result,
                    'recipient': recipient,
                    'delivery_method': 'iMessage' if 'iMessage' in result else 'SMS'
                }
            else:
                return {
                    'status': 'error',
                    'message': result,
                    'recipient': recipient
                }
            
        except Exception as e:
            logger.error(f"Failed to send message directly: {e}")
            return {
                'status': 'error',
                'message': f'Failed to send message: {str(e)}',
                'recipient': recipient
            }
    
    async def get_recent_messages(self, hours: int = 24, contact: Optional[str] = None) -> Dict[str, Any]:
        """Get recent messages directly using the mac_messages_mcp library."""
        try:
            # Import the function directly
            from mac_messages_mcp.messages import get_recent_messages
            
            # Call the function directly in a thread to avoid blocking
            import asyncio
            import concurrent.futures
            
            loop = asyncio.get_event_loop()
            with concurrent.futures.ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(
                    executor, 
                    get_recent_messages, 
                    hours,
                    contact
                )
            
            logger.info(f"Direct get_recent_messages result: {result}")
            
            # Parse the result (it's likely a string, need to convert to our format)
            if isinstance(result, str):
                # Simple parsing - in real implementation, would parse the string properly
                return {
                    'messages': [{'sender': 'Unknown', 'message': result, 'timestamp': 'Unknown'}],
                    'count': 1,
                    'status': 'success'
                }
            
            return {
                'messages': result if isinstance(result, list) else [],
                'count': len(result) if isinstance(result, list) else 0,
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Failed to get messages directly: {e}")
            return {
                'messages': [],
                'count': 0,
                'status': 'error'
            }
    
    def cleanup(self):
        """No cleanup needed for direct client."""
        pass

# Keep the old MCP client code but rename it
class MCPMessageClient:
    """Old MCP client - keeping for reference but not using."""
    
    def __init__(self):
        self.mcp_process = None
        self.request_id = 0
        self.initialized = False
    
    async def _get_next_id(self) -> int:
        """Get next request ID."""
        self.request_id += 1
        return self.request_id
    
    async def _ensure_mcp_process(self):
        """Ensure MCP process is running and initialized."""
        if self.mcp_process is None or self.mcp_process.poll() is not None:
            try:
                # Start the MCP server process using the local version
                self.mcp_process = subprocess.Popen(
                    ["python", "/Users/vinaynarahari/Desktop/Github/richard/mac_messages_mcp/main.py"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=0
                )
                
                # Initialize the MCP connection
                if not self.initialized:
                    init_request = {
                        "jsonrpc": "2.0",
                        "id": await self._get_next_id(),
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {
                                "roots": {
                                    "listChanged": True
                                },
                                "sampling": {}
                            },
                            "clientInfo": {
                                "name": "richard-orchestrator",
                                "version": "1.0.0"
                            }
                        }
                    }
                    
                    # Send initialization
                    request_line = json.dumps(init_request) + "\n"
                    self.mcp_process.stdin.write(request_line)
                    self.mcp_process.stdin.flush()
                    
                    # Wait for response
                    await asyncio.sleep(1)
                    self.initialized = True
                    
            except Exception as e:
                logger.error(f"Failed to start MCP process: {e}")
                raise
    
    async def _call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on the MCP server."""
        try:
            await self._ensure_mcp_process()
            
            request = {
                "jsonrpc": "2.0",
                "id": await self._get_next_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            
            # Log the request for debugging
            logger.info(f"Sending MCP request: {json.dumps(request)}")
            
            # Send the request
            request_line = json.dumps(request) + "\n"
            self.mcp_process.stdin.write(request_line)
            self.mcp_process.stdin.flush()
            
            # Read response with timeout
            try:
                # Give the server time to process
                await asyncio.sleep(2)
                
                # Try to read response
                response_line = self.mcp_process.stdout.readline()
                if response_line:
                    logger.info(f"MCP response: {response_line.strip()}")
                    response = json.loads(response_line.strip())
                    if "result" in response:
                        # For send_message, the result is the message itself
                        return {"status": "success", "message": response["result"]}
                    elif "error" in response:
                        logger.error(f"MCP tool error: {response['error']}")
                        return {"status": "error", "message": str(response["error"])}
                
                # If no response, try reading stderr for error info
                stderr_line = self.mcp_process.stderr.readline()
                if stderr_line:
                    logger.error(f"MCP stderr: {stderr_line.strip()}")
                
                return {"status": "error", "message": "No response from MCP server"}
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse MCP response: {e}")
                return {"status": "error", "message": "Invalid response from MCP server"}
                
        except Exception as e:
            logger.error(f"MCP tool call failed: {e}")
            return {"status": "error", "message": str(e)}
    
    async def send_message(self, recipient: str, message: str) -> Dict[str, Any]:
        """Send a message via iMessage/SMS through the MCP server."""
        try:
            result = await self._call_mcp_tool("tool_send_message", {
                "recipient": recipient,
                "message": message
            })
            
            # Check if the MCP call actually succeeded
            if result.get('status') == 'error':
                return {
                    'status': 'error',
                    'message': f'MCP Error: {result.get("message", "Unknown error")}',
                    'recipient': recipient
                }
            
            return {
                'status': 'success',
                'message': f'Message sent to {recipient}: {message}',
                'recipient': recipient,
                'delivery_method': 'iMessage'
            }
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return {
                'status': 'error',
                'message': f'Failed to send message: {str(e)}',
                'recipient': recipient
            }
    
    async def get_recent_messages(self, hours: int = 24, contact: Optional[str] = None) -> Dict[str, Any]:
        """Get recent messages from the Messages app."""
        try:
            arguments = {"hours": hours}
            if contact:
                arguments["contact"] = contact
                
            result = await self._call_mcp_tool("tool_get_recent_messages", arguments)
            
            if result.get('status') == 'error':
                return {
                    'messages': [],
                    'count': 0,
                    'status': 'error'
                }
            
            messages = result.get('messages', [])
            return {
                'messages': messages,
                'count': len(messages),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Failed to get messages: {e}")
            return {
                'messages': [],
                'count': 0,
                'status': 'error'
            }
    
    def cleanup(self):
        """Clean up MCP process."""
        if self.mcp_process:
            try:
                self.mcp_process.terminate()
                self.mcp_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.mcp_process.kill()
            except Exception:
                pass

# Global researcher instance
_researcher = WebResearcher()

# Global service instances
_direct_message_client = DirectMessageClient()
_imcp_client = iMCPClient()
_message_service = _direct_message_client  # Use direct for now, but we have iMCP available

@router.post("/web-researcher/research_question", response_model=ResearchResponse)
async def research_question(request: ResearchRequest) -> ResearchResponse:
    """Research a question by searching the web and analyzing content."""
    try:
        result = await _researcher.research_question(
            question=request.question,
            max_sources=request.max_sources
        )
        return ResearchResponse(**result)
    except Exception as e:
        logger.error(f"Research endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")

@router.get("/web-researcher/health")
async def health_check():
    """Health check for web researcher service."""
    return {"status": "healthy", "service": "web-researcher"}

@router.post("/mac-messages/send_message", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest) -> SendMessageResponse:
    """Send a message via iMessage/SMS."""
    try:
        result = await _message_service.send_message(
            recipient=request.recipient,
            message=request.message
        )
        return SendMessageResponse(**result)
    except Exception as e:
        logger.error(f"Send message endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@router.post("/mac-messages/get_recent_messages", response_model=GetMessagesResponse)
async def get_recent_messages(request: GetMessagesRequest) -> GetMessagesResponse:
    """Get recent messages from the Messages app."""
    try:
        result = await _message_service.get_recent_messages(
            hours=request.hours,
            contact=request.contact
        )
        return GetMessagesResponse(**result)
    except Exception as e:
        logger.error(f"Get messages endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get messages: {str(e)}")

@router.get("/mac-messages/health")
async def message_health_check():
    """Health check for messaging service."""
    return {"status": "healthy", "service": "mac-messages"}

@router.post("/imcp/search_contacts", response_model=ContactSearchResponse)
async def search_contacts(request: ContactSearchRequest) -> ContactSearchResponse:
    """Search contacts using iMCP."""
    try:
        result = await _imcp_client.search_contacts(
            query=request.query,
            max_results=request.max_results
        )
        return ContactSearchResponse(**result)
    except Exception as e:
        logger.error(f"Contact search endpoint error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search contacts: {str(e)}")

@router.get("/imcp/health")
async def imcp_health_check():
    """Health check for iMCP service."""
    return {"status": "healthy", "service": "imcp"}

# Cleanup on shutdown
import atexit

def cleanup():
    if _researcher.session:
        asyncio.create_task(_researcher.close_session())
    _message_service.cleanup()
    _imcp_client.cleanup()

atexit.register(cleanup)
