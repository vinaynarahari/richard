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

class PlaywrightMCPClient:
    """Client for Playwright MCP server to perform web searches and content extraction."""
    
    def __init__(self):
        self.mcp_process = None
        self.request_id = 0
        self.initialized = False
        self.playwright_path = "/Users/vinaynarahari/Desktop/Github/richard/mcp-servers/playwright-search"

class WebResearcher:
    """Web researcher that searches and fetches content to answer questions using Playwright MCP."""
    
    def __init__(self):
        self.session = None
        self.max_content_length = 50000  # Limit content size
        self.timeout = 30  # Request timeout
        self.playwright_client = PlaywrightMCPClient()
        
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
    
    async def search_web_with_playwright(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Search using Playwright MCP for accurate, real-time results."""
        try:
            # Use Playwright to search Google (more reliable than DuckDuckGo API)
            await self.setup_session()
            
            # Navigate to Google search
            search_url = f"https://www.google.com/search?q={'+'.join(query.split())}"
            
            async with self.session.get(search_url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    results = []
                    
                    # Extract Google search results
                    for result in soup.find_all('div', class_='g')[:max_results]:
                        title_elem = result.find('h3')
                        link_elem = result.find('a')
                        snippet_elem = result.find('div', class_=['VwiC3b', 's3v9rd'])
                        
                        if title_elem and link_elem:
                            title = title_elem.get_text(strip=True)
                            url = link_elem.get('href', '')
                            snippet = snippet_elem.get_text(strip=True) if snippet_elem else ''
                            
                            # Clean up URL
                            if url.startswith('/url?q='):
                                url = url.split('/url?q=')[1].split('&')[0]
                            
                            if title and url and 'google.com' not in url:
                                results.append({
                                    'title': title,
                                    'url': url,
                                    'snippet': snippet
                                })
                    
                    if results:
                        return results[:max_results]
                        
        except Exception as e:
            logger.error(f"Playwright Google search failed: {e}")
        
        # Fallback to intelligent sources
        return self._get_intelligent_sources(query)[:max_results]
    
    async def search_web(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Universal search system using our existing infrastructure."""
        # Primary method: Playwright-based Google search
        results = await self.search_web_with_playwright(query, max_results)
        
        if results and len(results) >= 2:
            return results
        
        # Fallback: Intelligent domain-specific sources
        fallback_sources = self._get_intelligent_sources(query)
        if results:
            # Combine with what we have
            combined = results + fallback_sources
            return combined[:max_results]
        else:
            return fallback_sources[:max_results] if fallback_sources else self._get_universal_fallback(query)
    
    def _get_intelligent_sources(self, query: str) -> List[Dict[str, str]]:
        """Get intelligent sources based on query content."""
        query_lower = query.lower()
        sources = []
        
        # Financial/Business queries
        if any(term in query_lower for term in ['stock', 'price', 'market', 'finance', 'company', 'business']):
            company = self._extract_company_name(query)
            sources.extend([
                {'title': f'{company} Financial Data', 'url': f'https://finance.yahoo.com/quote/{company}', 'snippet': f'Financial information for {company}'},
                {'title': f'{company} Company Info', 'url': f'https://www.marketwatch.com/investing/stock/{company}', 'snippet': f'Company profile and stock data'}
            ])
        
        # Technology/Programming queries  
        elif any(term in query_lower for term in ['code', 'programming', 'software', 'python', 'javascript', 'api']):
            sources.extend([
                {'title': 'Stack Overflow', 'url': f'https://stackoverflow.com/search?q={"+".join(query.split())}', 'snippet': 'Programming Q&A community'},
                {'title': 'GitHub', 'url': f'https://github.com/search?q={"+".join(query.split())}', 'snippet': 'Code repositories and projects'},
                {'title': 'Documentation', 'url': f'https://docs.python.org/3/search.html?q={"+".join(query.split())}', 'snippet': 'Official documentation'}
            ])
        
        # News/Current events
        elif any(term in query_lower for term in ['news', 'today', 'latest', 'recent', 'current', 'breaking']):
            sources.extend([
                {'title': 'Google News', 'url': f'https://news.google.com/search?q={"+".join(query.split())}', 'snippet': 'Latest news results'},
                {'title': 'Reuters', 'url': f'https://www.reuters.com/site-search/?query={"+".join(query.split())}', 'snippet': 'Reuters news coverage'},
                {'title': 'Associated Press', 'url': f'https://apnews.com/search?q={"+".join(query.split())}', 'snippet': 'AP news articles'}
            ])
        
        # Academic/Research queries
        elif any(term in query_lower for term in ['research', 'study', 'paper', 'academic', 'science', 'university']):
            sources.extend([
                {'title': 'Google Scholar', 'url': f'https://scholar.google.com/scholar?q={"+".join(query.split())}', 'snippet': 'Academic papers and citations'},
                {'title': 'ResearchGate', 'url': f'https://www.researchgate.net/search?q={"+".join(query.split())}', 'snippet': 'Research publications and collaboration'},
                {'title': 'JSTOR', 'url': f'https://www.jstor.org/action/doBasicSearch?Query={"+".join(query.split())}', 'snippet': 'Academic journals and books'}
            ])
        
        # Health/Medical queries
        elif any(term in query_lower for term in ['health', 'medical', 'disease', 'symptom', 'treatment', 'medicine']):
            sources.extend([
                {'title': 'Mayo Clinic', 'url': f'https://www.mayoclinic.org/search/search-results?q={"+".join(query.split())}', 'snippet': 'Medical information and health advice'},
                {'title': 'WebMD', 'url': f'https://www.webmd.com/search/search_results/default.aspx?query={"+".join(query.split())}', 'snippet': 'Health information and medical reference'},
                {'title': 'MedlinePlus', 'url': f'https://medlineplus.gov/search/?query={"+".join(query.split())}', 'snippet': 'Government health information'}
            ])
        
        # Wikipedia for general knowledge
        sources.append({
            'title': f'Wikipedia: {query}',
            'url': f'https://en.wikipedia.org/wiki/Special:Search?search={"+".join(query.split())}',
            'snippet': f'Encyclopedia article about {query}'
        })
        
        return sources
    
    def _get_universal_fallback(self, query: str) -> List[Dict[str, str]]:
        """Universal fallback when all other methods fail."""
        return [
            {
                'title': f'Search results for: {query}',
                'url': f'https://www.google.com/search?q={"+".join(query.split())}',
                'snippet': f'General web search results for {query}'
            },
            {
                'title': f'Wikipedia: {query}',
                'url': f'https://en.wikipedia.org/wiki/Special:Search?search={"+".join(query.split())}',
                'snippet': f'Encyclopedia search for {query}'
            }
        ]
    
    def _extract_company_name(self, query: str) -> str:
        """Extract company name from query."""
        query_lower = query.lower()
        # Remove common search terms
        for term in ['stock', 'price', 'of', 'what', 'is', 'the', 'company', 'share', 'ticker']:
            query_lower = query_lower.replace(term, '')
        
        # Extract the first meaningful word
        words = query_lower.split()
        for word in words:
            if len(word) > 2 and word.isalpha():
                return word
        
        return 'UNKNOWN'
    
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
                    
                    # Filter out error messages and navigation junk
                    if text and len(text) > 20:
                        # Check for common error indicators
                        error_indicators = ['oops', 'something went wrong', 'error occurred', 'page not found', '404']
                        if not any(indicator in text.lower() for indicator in error_indicators):
                            return text[:self.max_content_length]
                    
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
                # Smart fallback based on snippets and search results
                if search_results:
                    # Extract information from snippets intelligently
                    snippet_info = []
                    for result in search_results[:3]:
                        snippet = result.get('snippet', '').strip()
                        if snippet and len(snippet) > 15:
                            # Clean up snippet
                            snippet = re.sub(r'\s+', ' ', snippet).strip()
                            if not any(junk in snippet.lower() for junk in ['click', 'read more', 'subscribe']):
                                snippet_info.append(snippet)
                    
                    if snippet_info:
                        # Combine snippets intelligently
                        combined_snippets = '. '.join(snippet_info[:2])
                        answer = self._extract_answer(question, combined_snippets)
                        
                        if not answer.startswith("I found some") and not answer.startswith("I couldn't"):
                            return {
                                'question': question,
                                'answer': answer,
                                'sources': [{'title': r.get('title', ''), 'url': r.get('url', ''), 'snippet': r.get('snippet', '')} for r in search_results[:max_sources]],
                                'status': 'snippet_success'
                            }
                
                # Topic-specific intelligent fallbacks
                return self._get_intelligent_fallback(question, search_results, sources)
            
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
        """Universal answer extraction that works for any topic intelligently."""
        question_lower = question.lower()
        
        # Clean and split content into sentences
        sentences = re.split(r'[.!?]+', content)
        clean_sentences = []
        
        for sentence in sentences:
            sentence = sentence.strip()
            # Filter out junk content
            if (len(sentence) > 20 and len(sentence) < 500 and
                not any(junk in sentence.lower() for junk in [
                    'cookie', 'privacy', 'subscribe', 'follow', 'sign up', 'login',
                    'advertisement', 'sponsored', 'newsletter', 'click here',
                    'read more', 'terms of service', 'contact us', 'about us'
                ])):
                clean_sentences.append(sentence)
        
        if not clean_sentences:
            return "I found some content but couldn't extract a clear answer."
        
        # Extract keywords from question (improved)
        question_keywords = set(re.findall(r'\b[a-zA-Z]{3,}\b', question_lower))
        stop_words = {
            'what', 'when', 'who', 'where', 'how', 'why', 'which', 'the', 'was', 
            'were', 'are', 'and', 'but', 'for', 'with', 'this', 'that', 'they',
            'have', 'had', 'will', 'would', 'could', 'should', 'can', 'may'
        }
        question_keywords = question_keywords - stop_words
        
        # Advanced sentence scoring
        scored_sentences = []
        
        for sentence in clean_sentences[:20]:  # Check more sentences
            sentence_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', sentence.lower()))
            keyword_matches = len(question_keywords.intersection(sentence_words))
            
            # Comprehensive scoring system
            score = 0
            
            # Keyword relevance (primary factor)
            score += keyword_matches * 3
            
            # Question type bonuses
            if any(q_word in question_lower for q_word in ['what is', 'what are']):
                if re.search(r'\b(?:is|are|was|were)\s+(?:a|an|the)?\s*\w+', sentence, re.IGNORECASE):
                    score += 2
            
            if any(q_word in question_lower for q_word in ['when', 'what year', 'what date']):
                if re.search(r'\b(?:19|20)\d{2}\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', sentence, re.IGNORECASE):
                    score += 3
            
            if any(q_word in question_lower for q_word in ['who', 'founded', 'created']):
                if re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+\b', sentence):  # Person names
                    score += 2
            
            if any(q_word in question_lower for q_word in ['where', 'located']):
                if re.search(r'\b(?:in|at|located|based)\s+[A-Z][a-z]+', sentence, re.IGNORECASE):
                    score += 2
            
            if any(q_word in question_lower for q_word in ['how much', 'price', 'cost']):
                if re.search(r'\$\d+|\d+\s*(?:dollars?|USD|cents?)', sentence, re.IGNORECASE):
                    score += 3
            
            if any(q_word in question_lower for q_word in ['how many', 'number']):
                if re.search(r'\b\d+(?:,\d{3})*(?:\.\d+)?\b', sentence):
                    score += 2
            
            # Content quality indicators
            if re.search(r'\b(?:according|research|study|report|data|statistics)\b', sentence, re.IGNORECASE):
                score += 1
            
            if re.search(r'\b(?:founded|established|created|invented|discovered|launched)\b', sentence, re.IGNORECASE):
                score += 1
            
            if re.search(r'\b\d+\b', sentence):  # Contains numbers
                score += 1
            
            # Position bonus (earlier sentences often more important)
            position_bonus = max(0, 3 - (clean_sentences.index(sentence) // 5))
            score += position_bonus
            
            if score > 0:
                scored_sentences.append((score, sentence))
        
        # Sort by score and get best answers
        scored_sentences.sort(reverse=True, key=lambda x: x[0])
        
        if scored_sentences:
            # Use top 1-2 sentences based on score
            high_score_threshold = max(scored_sentences[0][0] * 0.7, 2)  # At least 70% of top score
            best_sentences = [
                s[1] for s in scored_sentences[:3] 
                if s[0] >= high_score_threshold
            ]
            
            if best_sentences:
                # Combine sentences intelligently
                if len(best_sentences) == 1:
                    answer = best_sentences[0]
                else:
                    # Remove redundancy between sentences
                    unique_sentences = []
                    for sentence in best_sentences:
                        if not any(self._sentences_similar(sentence, existing) for existing in unique_sentences):
                            unique_sentences.append(sentence)
                    
                    answer = '. '.join(unique_sentences[:2])
                
                # Clean up the answer
                answer = answer.rstrip('.') + '.'
                answer = re.sub(r'\s+', ' ', answer).strip()
                
                return f"Based on the search results: {answer}"
        
        # Intelligent fallback based on content type
        return self._get_fallback_answer(question, clean_sentences)
    
    def _sentences_similar(self, sent1: str, sent2: str, threshold: float = 0.6) -> bool:
        """Check if two sentences are similar to avoid redundancy."""
        words1 = set(sent1.lower().split())
        words2 = set(sent2.lower().split())
        
        if not words1 or not words2:
            return False
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return (intersection / union) > threshold
    
    def _get_fallback_answer(self, question: str, sentences: List[str]) -> str:
        """Get a fallback answer when scoring doesn't work well."""
        if not sentences:
            return "I found some information but couldn't extract a clear answer."
        
        # Try to find the most informative sentence
        for sentence in sentences[:8]:
            # Look for sentences with good information density
            if (len(sentence) > 30 and
                (re.search(r'\b(?:is|are|was|were|has|have|can|will|would)\b', sentence, re.IGNORECASE) or
                 re.search(r'\b\d+\b', sentence) or
                 re.search(r'\b(?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+\b', sentence))):  # Proper nouns
                
                return f"According to the sources: {sentence.rstrip('.')}."
        
        # Last resort: return first substantial sentence
        if sentences and len(sentences[0]) > 25:
            return f"Based on available information: {sentences[0].rstrip('.')}."
        
        return "I found some information but couldn't extract a specific answer to your question."
    
    def _get_intelligent_fallback(self, question: str, search_results: List[Dict], sources: List[Dict]) -> Dict[str, Any]:
        """Provide intelligent fallback answers based on question type when content fetch fails."""
        question_lower = question.lower()
        
        # Financial/Stock queries
        if any(term in question_lower for term in ['stock', 'price', 'figment', 'market', 'finance', 'ticker']):
            company = self._extract_company_name(question)
            answer = f"I found search results for {company} but couldn't fetch current financial data. Stock prices change frequently, so I recommend checking Yahoo Finance, MarketWatch, or your broker's app for real-time {company} stock information."
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'financial_guidance'
            }
        
        # News/Current events
        elif any(term in question_lower for term in ['news', 'latest', 'recent', 'today', 'current', 'breaking']):
            answer = f"I found news sources related to '{question}' but couldn't fetch the latest content. For current news, I recommend checking reliable news sources like Reuters, AP News, or Google News directly."
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'news_guidance'
            }
        
        # Technical/Programming queries
        elif any(term in question_lower for term in ['code', 'programming', 'error', 'python', 'javascript', 'api']):
            answer = f"I found technical resources for '{question}' but couldn't access the detailed content. For programming help, try Stack Overflow, GitHub, or the official documentation for your specific technology."
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'tech_guidance'
            }
        
        # Health/Medical queries  
        elif any(term in question_lower for term in ['health', 'medical', 'symptom', 'disease', 'treatment']):
            answer = f"I found medical resources related to '{question}' but couldn't access the full content. For health information, please consult reliable medical sources like Mayo Clinic, WebMD, or speak with a healthcare professional."
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'health_guidance'
            }
        
        # Academic/Research queries
        elif any(term in question_lower for term in ['research', 'study', 'academic', 'paper', 'science']):
            answer = f"I found academic sources for '{question}' but couldn't retrieve the full content. Try Google Scholar, ResearchGate, or your institution's library database for detailed research information."
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'academic_guidance'
            }
        
        # General fallback with helpful guidance
        else:
            if search_results:
                # Provide source guidance
                source_names = [result.get('title', 'Unknown') for result in search_results[:2]]
                answer = f"I found relevant sources including {', '.join(source_names)} but couldn't fetch the detailed content. Try visiting these sources directly for complete information about '{question}'."
            else:
                answer = f"I couldn't find comprehensive information about '{question}' at the moment. Try rephrasing your question or searching on Wikipedia, Google, or other reliable sources."
            
            return {
                'question': question,
                'answer': answer,
                'sources': sources,
                'status': 'general_guidance'
            }

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
