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
        # Maximum speed configuration with sensible defaults and env overrides
        try:
            import os as _os
            cpu_total = max(1, (_os.cpu_count() or 8))
            # Leave a couple cores free to keep UI responsive
            cpu_default = max(2, min(8, cpu_total - 2))
            env = _os.environ
        except Exception:
            cpu_default = 4
            env = {}

        def _int_env(name: str, default: int) -> int:
            try:
                return int(env.get(name, default))
            except Exception:
                return default

        def _float_env(name: str, default: float) -> float:
            try:
                return float(env.get(name, default))
            except Exception:
                return default

        # Defaults tuned for smooth streaming and lower memory
        opt_temperature = temperature if temperature is not None else _float_env("OLLAMA_TEMPERATURE", 0.2)
        opt_num_predict = _int_env("OLLAMA_NUM_PREDICT", max_tokens or 256)
        opt_num_ctx = _int_env("OLLAMA_NUM_CTX", 1024)
        opt_num_thread = _int_env("OLLAMA_NUM_THREAD", cpu_default)
        opt_num_gpu = _int_env("OLLAMA_NUM_GPU", -1)
        opt_top_k = _int_env("OLLAMA_TOP_K", 30)
        opt_top_p = _float_env("OLLAMA_TOP_P", 0.9)
        opt_repeat_penalty = _float_env("OLLAMA_REPEAT_PENALTY", 1.05)
        opt_num_keep = _int_env("OLLAMA_NUM_KEEP", 16)
        opt_keep_alive = env.get("OLLAMA_KEEP_ALIVE", "10m")
        opt_low_vram = env.get("OLLAMA_LOW_VRAM", "false").lower() in ("1", "true", "yes")

        options: Dict[str, Any] = {
            "temperature": opt_temperature,
            "num_predict": opt_num_predict,
            "num_ctx": opt_num_ctx,
            "num_gpu": opt_num_gpu,
            "num_thread": opt_num_thread,
            "top_k": opt_top_k,
            "top_p": opt_top_p,
            "repeat_penalty": opt_repeat_penalty,
            "num_keep": opt_num_keep,
            "seed": -1,
            "tfs_z": 1.0,
            "typical_p": 1.0,
            "mirostat": 0,
        }
        # Only include keep_alive if set (older servers ignore it otherwise)
        if opt_keep_alive:
            payload["keep_alive"] = opt_keep_alive
        if opt_low_vram:
            options["low_vram"] = True

        payload["options"] = options

        if system:
            # Add tool descriptions to system prompt since Ollama doesn't support function calls
            if tools:
                system += "\n\nIMPORTANT: NEVER use <think> tags. Just output function calls directly.\n\nAvailable functions:\n"
                for tool in tools:
                    func = tool["function"]
                    system += f"- {func['name']}: {func['description']}\n"
                system += "\nFor email requests, immediately respond with: CALL_create_gmail_draft(to=[\"email@domain.com\"], subject=\"Subject\", body_markdown=\"Content\")\nNO explanations or thinking. Just the function call."
                system += "\nYou also have browsing tools: CALL_web_search(query=\"...\", max_results=5) and CALL_web_fetch(url=\"...\", max_chars=4000). Use them for fresh facts, current events, or when you are uncertain. Do not invent other tools."
            
            # prepend as system message if not already present
            messages = [{"role": "system", "content": system}] + [m for m in messages if m.get("role") != "system"]
            payload["messages"] = messages

        # Manual retry/backoff for transient connection failures to Ollama
        attempt = 0
        last_exc: Optional[Exception] = None
        backoffs = [0.2, 0.5, 1.0, 2.0]  # total ~3.7s
        # Emit diagnostics if requested
        import os as _os
        if _os.getenv("DEBUG_OLLAMA", "").lower() in ("1", "true", "yes"):
            print(f"[OllamaClient] chat_stream -> url={url} model={model}", flush=True)
            print(f"[OllamaClient] payload={json.dumps(payload, indent=2)}", flush=True)
        else:
            print(f"[OllamaClient] chat_stream -> url={url} model={model}", flush=True)
        while attempt <= len(backoffs):
            try:
                # quick HEAD to detect listener early; tolerate 404 on HEAD for older servers
                try:
                    head_resp = await self._client.get(self.base_url + "/", timeout=5.0)
                    print(f"[OllamaClient] GET / -> {head_resp.status_code}", flush=True)
                except Exception as ping_err:
                    print(f"[OllamaClient] GET / failed on attempt {attempt+1}: {ping_err}", flush=True)
                async with self._client.stream("POST", url, json=payload) as resp:
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        # Fallback: if /api/chat is not supported (older Ollama), try /api/generate streaming
                        if e.response is not None and e.response.status_code == 404:
                            print("[OllamaClient] /api/chat -> 404. Falling back to /api/generate (compat mode)", flush=True)
                            async for chunk in self._generate_fallback_stream(model, messages, payload.get("options", {})):
                                yield chunk
                            last_exc = None
                            break
                        raise
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

    async def _generate_fallback_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Fallback to /api/generate for older Ollama servers without /api/chat.
        Also auto-selects an installed model if the requested one is not available."""
        # Build a simple prompt from messages
        def to_prompt(msgs: List[Dict[str, Any]]) -> str:
            lines: List[str] = []
            for m in msgs:
                role = (m.get("role") or "user").strip().upper()
                content = (m.get("content") or "").strip()
                # Avoid duplicating empty system lines
                if not content:
                    continue
                if role == "SYSTEM":
                    lines.append(f"SYSTEM: {content}")
                elif role == "USER":
                    lines.append(f"USER: {content}")
                else:
                    lines.append(f"{role}: {content}")
            lines.append("ASSISTANT:")
            return "\n\n".join(lines)

        prompt = to_prompt(messages)

        # If the model appears unavailable, pick a valid one
        try:
            models = await self.list_models()
        except Exception:
            models = []
        chosen_model = model
        if models and not any(chosen_model in m for m in models):
            # choose first matching popular model; else first listed
            prefs = [
                "gemma", "gemma2", "gemma3",
                "llama3", "llama3.1",
                "phi3",
                "qwen", "qwen2", "qwen2.5",
                "mistral", "mixtral",
            ]
            picked = None
            for p in prefs:
                for m in models:
                    if p in m:
                        picked = m
                        break
                if picked:
                    break
            if not picked:
                picked = models[0]
            print(f"[OllamaClient] Model '{model}' not found. Using installed model: {picked}", flush=True)
            chosen_model = picked

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": chosen_model,
            "prompt": prompt,
            "stream": True,
            "options": options or {},
        }
        print(f"[OllamaClient] generate_fallback -> url={url}", flush=True)
        print(f"[OllamaClient] generate_fallback payload={json.dumps(payload, indent=2)}", flush=True)
        async with self._client.stream("POST", url, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
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

    async def list_models(self) -> List[str]:
        """Return available Ollama model names from /api/tags, tolerant to schema differences."""
        try:
            r = await self._client.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
            data = r.json()
            names: List[str] = []
            if isinstance(data, dict):
                models = data.get("models") or []
                for m in models:
                    if isinstance(m, dict):
                        name = m.get("name") or m.get("model")
                        if isinstance(name, str) and name:
                            names.append(name)
            return names
        except Exception as e:
            print(f"[OllamaClient] list_models failed: {e}", flush=True)
            return []
