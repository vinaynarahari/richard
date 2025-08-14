from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, AnyHttpUrl
from typing import List, Optional, Tuple
import time
import os
import random
import re
import httpx

try:
    from duckduckgo_search import DDGS  # type: ignore
except Exception as e:
    DDGS = None  # Will error on first use with helpful message

router = APIRouter(prefix="/search", tags=["search"]) 

# Simple in-memory cache to reduce rate limits (very small, short TTL)
_CACHE: dict[str, Tuple[float, List["WebSearchResult"]]] = {}
_CACHE_TTL_SECONDS = 180.0

# DDG simple client-side rate limiter (avoid 202 ratelimit)
_DDG_MIN_INTERVAL = 1.2
_DDG_LAST_CALL_TS: float = 0.0


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = None


def _cache_get(q: str) -> Optional[List[WebSearchResult]]:
    now = time.time()
    entry = _CACHE.get(q)
    if not entry:
        return None
    ts, results = entry
    if now - ts > _CACHE_TTL_SECONDS:
        _CACHE.pop(q, None)
        return None
    return results


def _cache_put(q: str, results: List[WebSearchResult]) -> None:
    _CACHE[q] = (time.time(), results)


def _ddg_wait() -> None:
    global _DDG_LAST_CALL_TS
    now = time.time()
    elapsed = now - _DDG_LAST_CALL_TS
    if elapsed < _DDG_MIN_INTERVAL:
        # jitter to avoid burst patterns
        time.sleep((_DDG_MIN_INTERVAL - elapsed) + random.uniform(0.05, 0.25))
    _DDG_LAST_CALL_TS = time.time()


_domain_re = re.compile(r"\b([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}\b")


async def _try_fetch_title_and_snippet(url: str) -> Tuple[str, Optional[str]]:
    title, snippet = "", None
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept-Language": "en-US,en;q=0.9",
        }) as client:
            r = await client.get(url)
            r.raise_for_status()
            html = r.text
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if m:
            title = re.sub(r"<[^>]+>", " ", m.group(1)).strip()
        # crude snippet from text content
        text = _strip_html(html)
        if text:
            snippet = text[:300]
    except Exception as e:
        print(f"[search.web] direct fetch failed: {e}")
    return title or url, snippet


async def _provider_brave(q: str, max_results: int) -> Optional[List[WebSearchResult]]:
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
            "User-Agent": "Richard/1.0"
        }) as client:
            r = await client.get("https://api.search.brave.com/res/v1/web/search", params={"q": q, "count": max_results})
            r.raise_for_status()
            data = r.json()
        results: List[WebSearchResult] = []
        for item in (data.get("web", {}).get("results") or [])[:max_results]:
            title = item.get("title") or ""
            url = item.get("url") or ""
            snippet = item.get("description") or None
            if title and url:
                results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        return results or None
    except Exception as e:
        print(f"[search.web] Brave provider failed: {e}")
        return None


async def _provider_serper(q: str, max_results: int) -> Optional[List[WebSearchResult]]:
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
            "User-Agent": "Richard/1.0",
        }) as client:
            r = await client.post("https://google.serper.dev/search", json={"q": q, "num": max_results})
            r.raise_for_status()
            data = r.json()
        results: List[WebSearchResult] = []
        for item in (data.get("organic") or [])[:max_results]:
            title = item.get("title") or ""
            url = item.get("link") or ""
            snippet = item.get("snippet") or None
            if title and url:
                results.append(WebSearchResult(title=title, url=url, snippet=snippet))
        return results or None
    except Exception as e:
        print(f"[search.web] Serper provider failed: {e}")
        return None


@router.get("/web", response_model=List[WebSearchResult])
async def web_search(q: str = Query(..., min_length=2), max_results: int = Query(5, ge=1, le=15)) -> List[WebSearchResult]:
    # Serve from cache if available
    cached = _cache_get(q)
    if cached is not None:
        return cached[:max_results]

    # If the query contains a domain, return that site directly as top result
    dom_match = _domain_re.search(q)
    if dom_match:
        domain = dom_match.group(0)
        scheme = "https"
        url = f"{scheme}://{domain}"
        title, snippet = await _try_fetch_title_and_snippet(url)
        direct = [WebSearchResult(title=title, url=url, snippet=snippet)]
        _cache_put(q, direct)
        return direct

    # Prefer reliable providers automatically when keys are present (Google-backed first)
    serper = await _provider_serper(q, max_results)
    if serper:
        _cache_put(q, serper)
        return serper
    brave = await _provider_brave(q, max_results)
    if brave:
        _cache_put(q, brave)
        return brave

    # Still honor explicit override if set (may force a specific provider)
    provider = (os.getenv("RICHARD_SEARCH_PROVIDER") or "").strip().lower()
    if provider == "brave":
        brave = await _provider_brave(q, max_results)
        if brave:
            _cache_put(q, brave)
            return brave
    if provider == "serper":
        serper = await _provider_serper(q, max_results)
        if serper:
            _cache_put(q, serper)
            return serper

    if DDGS is None:
        # As a last resort, try direct DuckDuckGo lite scrape; otherwise error
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get("https://lite.duckduckgo.com/lite/", params={"q": q})
                r.raise_for_status()
                html = r.text
            # Extremely rough extraction for titles/links
            link_re = re.compile(r'<a href="(http[^"]+)"[^>]*>([^<]+)</a>')
            results = [WebSearchResult(title=t.strip(), url=u, snippet=None) for u, t in link_re.findall(html)[:max_results]]
            if results:
                _cache_put(q, results)
                return results
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="duckduckgo_search not installed and no alternative provider configured.")

    # 1) Try DDGS default backend
    try:
        _ddg_wait()
        results: List[WebSearchResult] = []
        with DDGS() as ddgs:  # type: ignore[attr-defined]
            for r in ddgs.text(q, max_results=max_results, safesearch="off"):
                title = r.get("title") or ""
                href = r.get("href") or r.get("link") or ""
                body = r.get("body") or r.get("snippet") or None
                if title and href:
                    results.append(WebSearchResult(title=title, url=href, snippet=body))
        if results:
            _cache_put(q, results)
            return results
    except Exception as e:
        print(f"[search.web] DDGS default backend failed: {e}")

    # 2) Fallback: DDGS html backend (less likely to be blocked)
    try:
        time.sleep(0.6)
        results = []
        _ddg_wait()
        with DDGS() as ddgs:  # type: ignore[attr-defined]
            for r in ddgs.text(q, max_results=max_results, safesearch="off", backend="html"):
                title = r.get("title") or ""
                href = r.get("href") or r.get("link") or ""
                body = r.get("body") or r.get("snippet") or None
                if title and href:
                    results.append(WebSearchResult(title=title, url=href, snippet=body))
        if results:
            _cache_put(q, results)
            return results
    except Exception as e:
        print(f"[search.web] DDGS html backend failed: {e}")

    # 3) DuckDuckGo HTML endpoints
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Accept-Language": "en-US,en;q=0.9",
        }) as client:
            r = await client.get("https://html.duckduckgo.com/html/", params={"q": q})
            if r.status_code in (429, 202):
                await client.aclose()
                time.sleep(0.6)
                async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, headers={
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                }) as client2:
                    r = await client2.get("https://lite.duckduckgo.com/lite/", params={"q": q})
            r.raise_for_status()
            html = r.text
        # Extract results roughly
        link_re = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE)
        snip_re = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>.*?</a>.*?<a[^>]*>.*?</a>.*?<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', re.IGNORECASE | re.DOTALL)
        links = link_re.findall(html)
        snippets_map = {m[0]: re.sub(r"<[^>]+>", " ", m[1]).strip() for m in snip_re.findall(html)}
        results = []
        for href, raw_title in links[:max_results]:
            title = re.sub(r"<[^>]+>", " ", raw_title).strip()
            if title and href:
                results.append(WebSearchResult(title=title, url=href, snippet=snippets_map.get(href)))
        if results:
            _cache_put(q, results)
            return results
    except Exception as e:
        print(f"[search.web] HTML scrape fallback failed: {e}")

    # 4) Final: optional paid provider if configured even if provider override not set
    brave = await _provider_brave(q, max_results)
    if brave:
        _cache_put(q, brave)
        return brave
    serper = await _provider_serper(q, max_results)
    if serper:
        _cache_put(q, serper)
        return serper

    raise HTTPException(status_code=500, detail="Web search failed (all backends)")


def _strip_html(html: str) -> str:
    # Remove script/style blocks
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Unescape minimal entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


class FetchResponse(BaseModel):
    url: str
    status: int
    content: str


@router.get("/fetch", response_model=FetchResponse)
async def fetch(url: AnyHttpUrl, max_chars: int = Query(4000, ge=200, le=20000)) -> FetchResponse:
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(str(url), headers={"User-Agent": "Mozilla/5.0 (compatible; RichardBot/1.0)"})
        content_type = r.headers.get("content-type", "")
        text = r.text
        if "text/html" in content_type.lower():
            text = _strip_html(text)
        if len(text) > max_chars:
            text = text[:max_chars]
        return FetchResponse(url=str(url), status=r.status_code, content=text)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"HTTP error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 