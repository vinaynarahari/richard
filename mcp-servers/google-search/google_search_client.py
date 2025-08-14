"""Google Search client for the MCP server."""

import os
from typing import Any, Dict, List, Optional
import httpx
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class GoogleSearchClient:
    """Google Search client that provides web, image, and news search capabilities for MCP."""
    
    def __init__(self, api_key: Optional[str] = None, search_engine_id: Optional[str] = None):
        """Initialize Google Search client with API key and search engine ID."""
        # For now, use placeholders since we don't have search API keys set up
        # In production, this would use the Google OAuth credentials
        self.api_key = api_key or os.getenv("GOOGLE_SEARCH_API_KEY") or "placeholder"
        self.search_engine_id = search_engine_id or os.getenv("GOOGLE_SEARCH_ENGINE_ID") or "placeholder"
        
        try:
            self.service = build("customsearch", "v1", developerKey=self.api_key)
        except Exception:
            # For testing without real API keys
            self.service = None
    
    async def web_search(
        self, 
        query: str, 
        num_results: int = 10, 
        start_index: int = 1,
        site_search: Optional[str] = None,
        file_type: Optional[str] = None,
        date_restrict: Optional[str] = None
    ) -> Dict[str, Any]:
        """Perform a web search using Google Custom Search API."""
        if not self.service:
            raise ValueError("Google Search client not initialized. Set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID environment variables.")
        try:
            kwargs = {
                "q": query,
                "cx": self.search_engine_id,
                "num": min(num_results, 10),  # API limit is 10 per request
                "start": start_index
            }
            
            # Add optional parameters
            if site_search:
                kwargs["siteSearch"] = site_search
            
            if file_type:
                kwargs["fileType"] = file_type
            
            if date_restrict:
                kwargs["dateRestrict"] = date_restrict
            
            response = self.service.cse().list(**kwargs).execute()
            
            # Format results
            results = []
            for item in response.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "displayLink": item.get("displayLink", ""),
                    "formattedUrl": item.get("formattedUrl", ""),
                    "pagemap": item.get("pagemap", {})
                })
            
            return {
                "query": query,
                "searchInformation": response.get("searchInformation", {}),
                "results": results,
                "totalResults": response.get("searchInformation", {}).get("totalResults", "0"),
                "searchTime": response.get("searchInformation", {}).get("searchTime", 0)
            }
        
        except HttpError as e:
            raise RuntimeError(f"Google Search API error: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to perform web search: {str(e)}") from e
    
    async def image_search(
        self,
        query: str,
        num_results: int = 10,
        start_index: int = 1,
        image_size: Optional[str] = None,
        image_type: Optional[str] = None,
        safe_search: str = "active"
    ) -> Dict[str, Any]:
        """Perform an image search using Google Custom Search API."""
        try:
            kwargs = {
                "q": query,
                "cx": self.search_engine_id,
                "searchType": "image",
                "num": min(num_results, 10),  # API limit is 10 per request
                "start": start_index,
                "safe": safe_search
            }
            
            # Add optional parameters
            if image_size:
                kwargs["imgSize"] = image_size
            
            if image_type:
                kwargs["imgType"] = image_type
            
            response = self.service.cse().list(**kwargs).execute()
            
            # Format results
            results = []
            for item in response.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "displayLink": item.get("displayLink", ""),
                    "snippet": item.get("snippet", ""),
                    "mime": item.get("mime", ""),
                    "fileFormat": item.get("fileFormat", ""),
                    "image": {
                        "contextLink": item.get("image", {}).get("contextLink", ""),
                        "height": item.get("image", {}).get("height", 0),
                        "width": item.get("image", {}).get("width", 0),
                        "byteSize": item.get("image", {}).get("byteSize", 0),
                        "thumbnailLink": item.get("image", {}).get("thumbnailLink", ""),
                        "thumbnailHeight": item.get("image", {}).get("thumbnailHeight", 0),
                        "thumbnailWidth": item.get("image", {}).get("thumbnailWidth", 0)
                    }
                })
            
            return {
                "query": query,
                "searchInformation": response.get("searchInformation", {}),
                "results": results,
                "totalResults": response.get("searchInformation", {}).get("totalResults", "0"),
                "searchTime": response.get("searchInformation", {}).get("searchTime", 0)
            }
        
        except HttpError as e:
            raise RuntimeError(f"Google Image Search API error: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to perform image search: {str(e)}") from e
    
    async def news_search(
        self,
        query: str,
        num_results: int = 10,
        start_index: int = 1,
        date_restrict: Optional[str] = None,
        sort_by: str = "relevance"
    ) -> Dict[str, Any]:
        """Perform a news search using Google Custom Search API."""
        try:
            # For news search, we can use regular web search with news-specific query modifications
            news_query = f"{query} site:news.google.com OR site:cnn.com OR site:bbc.com OR site:reuters.com OR site:ap.org"
            
            kwargs = {
                "q": news_query,
                "cx": self.search_engine_id,
                "num": min(num_results, 10),  # API limit is 10 per request
                "start": start_index
            }
            
            # Add optional parameters
            if date_restrict:
                kwargs["dateRestrict"] = date_restrict
            
            if sort_by == "date":
                kwargs["sort"] = "date"
            
            response = self.service.cse().list(**kwargs).execute()
            
            # Format results
            results = []
            for item in response.get("items", []):
                # Extract publication date from pagemap if available
                pub_date = ""
                pagemap = item.get("pagemap", {})
                if "metatags" in pagemap and pagemap["metatags"]:
                    metatag = pagemap["metatags"][0]
                    pub_date = metatag.get("article:published_time", "") or metatag.get("pubdate", "")
                
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "displayLink": item.get("displayLink", ""),
                    "formattedUrl": item.get("formattedUrl", ""),
                    "publishedDate": pub_date,
                    "source": item.get("displayLink", "").replace("www.", ""),
                    "pagemap": pagemap
                })
            
            return {
                "query": query,
                "searchInformation": response.get("searchInformation", {}),
                "results": results,
                "totalResults": response.get("searchInformation", {}).get("totalResults", "0"),
                "searchTime": response.get("searchInformation", {}).get("searchTime", 0)
            }
        
        except HttpError as e:
            raise RuntimeError(f"Google News Search API error: {str(e)}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to perform news search: {str(e)}") from e