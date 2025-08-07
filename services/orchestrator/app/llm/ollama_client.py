import asyncio
import json
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


class OllamaClient:
    """
    Minimal async client for Ollama chat + embeddings with streaming.
    Base URL is typically http://127.0.0.1:11434
    """

    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: float = 120.0):
        # Allow overriding via env var to move off default 11434
        # Example: OLLAMA_HOST=http://127.0.0.1:11435
        import os as _os
        env_base = _os.getenv("OLLAMA_HOST")
        if env_base:
            base_url = env_base
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Robust client with small connection pool and retries via manual backoff
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        self._client = httpx.AsyncClient(timeout=timeout, limits=limits)

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
        Streams chat completion tokens from Ollama. Yields JSON dict chunks.
        Message format is OpenAI-like:
            [{"role": "system"|"user"|"assistant", "content": "..."}]
        """
        url = f"{self.base_url}/api/chat"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        # Speed optimizations
        payload["options"] = {
            "temperature": temperature or 0.7,
            "num_predict": max_tokens or 512,  # Limit response length
            "num_ctx": 2048,  # Smaller context window
            "num_gpu": -1,  # Use all GPU
            "num_thread": 8,  # Use more CPU threads
        }
        if system:
            # Add tool descriptions to system prompt since Ollama doesn't support function calls
            if tools:
                system += "\n\nIMPORTANT: NEVER use <think> tags. Just output function calls directly.\n\nAvailable functions:\n"
                for tool in tools:
                    func = tool["function"]
                    system += f"- {func['name']}: {func['description']}\n"
                system += "\nFor email requests, immediately respond with: CALL_create_gmail_draft(to=[\"email@domain.com\"], subject=\"Subject\", body_markdown=\"Content\")\nNO explanations or thinking. Just the function call."
            
            # prepend as system message if not already present
            messages = [{"role": "system", "content": system}] + [m for m in messages if m.get("role") != "system"]
            payload["messages"] = messages

        # Manual retry/backoff for transient connection failures to Ollama
        attempt = 0
        last_exc: Optional[Exception] = None
        backoffs = [0.2, 0.5, 1.0, 2.0]  # total ~3.7s
        # Emit clear diagnostics before attempting connection
        print(f"[OllamaClient] chat_stream -> url={url} model={model}", flush=True)
        print(f"[OllamaClient] payload={json.dumps(payload, indent=2)}", flush=True)
        while attempt <= len(backoffs):
            try:
                # quick HEAD to detect listener early; tolerate 404 on HEAD for older servers
                try:
                    head_resp = await self._client.get(self.base_url + "/", timeout=5.0)
                    print(f"[OllamaClient] GET / -> {head_resp.status_code}", flush=True)
                except Exception as ping_err:
                    print(f"[OllamaClient] GET / failed on attempt {attempt+1}: {ping_err}", flush=True)
                async with self._client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        # Ollama streams JSON lines
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            if line.startswith("data:"):
                                try:
                                    data = json.loads(line[5:].strip())
                                except Exception:
                                    continue
                            else:
                                continue
                        yield data
                # If we finished streaming without error, break the retry loop
                last_exc = None
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError) as e:
                last_exc = e
                print(f"[OllamaClient] attempt {attempt+1} failed: {type(e).__name__} -> {e}", flush=True)
                if attempt == len(backoffs):
                    # Surface a deterministic message so UI can show root cause
                    raise RuntimeError(f"Ollama connection failed after {attempt+1} attempts to {self.base_url}. Last error: {e}") from e
                await asyncio.sleep(backoffs[attempt])
                attempt += 1
            except httpx.HTTPStatusError:
                # Non-2xx are not retried here; propagate so caller can surface meaningful error
                raise
                if not line:
                    continue
                # Ollama streams JSON lines
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    # Some builds may send "data: {...}" SSE-like lines
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[5:].strip())
                        except Exception:
                            continue
                    else:
                        continue
                yield data

    async def embeddings(self, model: str, input_texts: List[str]) -> List[List[float]]:
        """
        Calls Ollama embeddings endpoint. Returns list of vectors (one per input).
        """
        url = f"{self.base_url}/api/embeddings"
        vectors: List[List[float]] = []
        for text in input_texts:
            payload = {"model": model, "prompt": text}
            r = await self._client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
            vec = data.get("embedding")
            if not isinstance(vec, list):
                raise RuntimeError("Invalid embedding response from Ollama")
            vectors.append(vec)
            # Be nice in tight loops
            await asyncio.sleep(0)
        return vectors
