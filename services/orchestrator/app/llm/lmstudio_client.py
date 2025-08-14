from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


class OpenAICompatClient:
    """
    Minimal async client for OpenAI-compatible chat endpoints (LM Studio).
    Base URL example: http://127.0.0.1:1234
    """

    def __init__(self, base_url: str = "http://127.0.0.1:1234", timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        # Conservative optimizations for localhost
        limits = httpx.Limits(max_keepalive_connections=10, max_connections=20, keepalive_expiry=30.0)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=2.0, read=timeout, write=10.0, pool=2.0),
            limits=limits,
            http2=False  # HTTP/1.1 is faster for localhost
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        system: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Streams chat completion tokens from an OpenAI-compatible API. Yields JSON dict chunks.
        We normalize to {"message": {"content": str}} for text pieces; emit {"done": True} at end.
        """
        url = f"{self.base_url}/v1/chat/completions"

        # Prepend system message if provided
        if system:
            # If tools are provided, append their descriptions into the system message
            if tools:
                system += "\n\nIMPORTANT: NEVER use <think> tags. Just output function calls directly.\n\nAvailable functions:\n"
                for tool in tools:
                    func = tool["function"]
                    system += f"- {func['name']}: {func['description']}\n"
                system += "\nYou also have browsing tools: CALL_web_search(query=\"...\", max_results=5) and CALL_web_fetch(url=\"...\", max_chars=4000). Use them for fresh facts."
            # Place system at the front
            messages = [{"role": "system", "content": system}] + [m for m in messages if m.get("role") != "system"]

        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            # LM Studio performance optimizations
            "top_p": 0.95,  # Slightly more focused sampling
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)

        print(f"[OpenAICompatClient] chat_stream -> url={url} model={model}", flush=True)

        async with self._client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[5:].strip()
                if not data_str:
                    continue
                if data_str == "[DONE]":
                    yield {"done": True}
                    break
                try:
                    data = json.loads(data_str)
                    # Fast path: direct access for speed
                    choices = data.get("choices")
                    if choices and len(choices) > 0:
                        delta = choices[0].get("delta")
                        if delta:
                            content_piece = delta.get("content")
                            if content_piece:
                                yield {"message": {"content": content_piece}}
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    # Skip malformed chunks
                    continue

    async def list_models(self) -> List[str]:
        try:
            r = await self._client.get(f"{self.base_url}/v1/models", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            ids: List[str] = []
            for m in (data.get("data") or []):
                mid = m.get("id")
                if isinstance(mid, str):
                    ids.append(mid)
            return ids
        except Exception as e:
            print(f"[OpenAICompatClient] list_models failed: {e}", flush=True)
            return []

    async def embeddings(self, model: str, input_texts: List[str]) -> List[List[float]]:
        url = f"{self.base_url}/v1/embeddings"
        vectors: List[List[float]] = []
        for text in input_texts:
            payload = {"model": model, "input": text}
            r = await self._client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            items = data.get("data") or []
            if not items:
                raise RuntimeError("Invalid embedding response from LM Studio")
            vec = items[0].get("embedding")
            if not isinstance(vec, list):
                raise RuntimeError("Invalid embedding vector type from LM Studio")
            vectors.append(vec)
            await asyncio.sleep(0)
        return vectors 