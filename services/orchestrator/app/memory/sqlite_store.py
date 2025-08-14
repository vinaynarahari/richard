from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..llm.ollama_client import OllamaClient
from ..llm.lmstudio_client import OpenAICompatClient  # NEW


DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "app/memory.db")).resolve()
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")  # OpenAI-compatible default


@dataclass
class MemoryItem:
    id: Optional[int]
    kind: str
    text: str
    meta: Dict[str, Any]
    vector: Optional[List[float]]


class SQLiteMemory:
    """
    Simple SQLite-backed memory store with cosine similarity search over embeddings.
    Uses LM Studio (OpenAI-compatible) if LLM_PROVIDER=lmstudio, else Ollama.
    Falls back to a hashing-based embedding if providers are unavailable.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, ollama: Optional[OllamaClient] = None):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        # Select embedding client
        provider = (os.getenv("LLM_PROVIDER") or "lmstudio").strip().lower()
        if provider == "lmstudio":
            base = os.getenv("LMSTUDIO_HOST", "http://127.0.0.1:1234")
            self._embed_client = OpenAICompatClient(base_url=base)
            self._embed_kind = "lmstudio"
        else:
            base = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
            self._embed_client = ollama or OllamaClient(base_url=base)
            self._embed_kind = "ollama"

    async def _ensure(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    meta TEXT NOT NULL,
                    vector BLOB
                )
                """
            )
            self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        # Close HTTP client if LM Studio
        try:
            if isinstance(self._embed_client, OpenAICompatClient):
                await self._embed_client.aclose()
        except Exception:
            pass

    async def _embed(self, texts: List[str]) -> List[List[float]]:
        # Try provider embeddings
        try:
            if self._embed_kind == "lmstudio":
                return await self._embed_client.embeddings(EMBED_MODEL, texts)  # type: ignore[arg-type]
            else:
                # Ollama embeddings expects prompt per call
                vectors: List[List[float]] = []
                for t in texts:
                    v = await self._embed_client.embeddings(EMBED_MODEL, [t])  # type: ignore[union-attr]
                    # Ollama client returns list for each input
                    vectors.append(v[0])
                return vectors
        except Exception as e:
            # Fallback: hashing-based 256-dim embedding (deterministic)
            import math
            import hashlib
            dims = 256
            vecs: List[List[float]] = []
            for t in texts:
                accum = [0.0] * dims
                for token in t.lower().split():
                    h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                    idx = h % dims
                    accum[idx] += 1.0
                # L2 normalize
                norm = math.sqrt(sum(x * x for x in accum)) or 1.0
                vecs.append([x / norm for x in accum])
            return vecs

    async def insert(self, kind: str, text: str, meta: Optional[Dict[str, Any]] = None) -> int:
        await self._ensure()
        meta = meta or {}
        vectors = await self._embed([text])
        vector = json.dumps(vectors[0]).encode("utf-8")
        cur = self._conn.execute(
            "INSERT INTO memory(kind, text, meta, vector) VALUES(?,?,?,?)",
            (kind, text, json.dumps(meta, ensure_ascii=False), vector),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    async def insert_with_embedding(self, kind: str, text: str, meta: Optional[Dict[str, Any]] = None) -> int:
        return await self.insert(kind, text, meta)

    async def search(self, query: str, top_k: int = 5, kind: Optional[str] = None) -> List[Tuple[MemoryItem, float]]:
        await self._ensure()
        # Load all vectors (small scale)
        rows = self._conn.execute(
            "SELECT id, kind, text, meta, vector FROM memory"
        ).fetchall()
        if not rows:
            return []
        # Filter by kind if provided
        if kind:
            rows = [r for r in rows if r[1] == kind]
        # Embed query
        qv = (await self._embed([query]))[0]
        # Compute cosine similarity
        import math
        def cos(a: List[float], b: List[float]) -> float:
            s = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a)) or 1.0
            nb = math.sqrt(sum(y * y for y in b)) or 1.0
            return s / (na * nb)
        scored: List[Tuple[MemoryItem, float]] = []
        for id_, kind_, text_, meta_json, vec_blob in rows:
            try:
                vec = json.loads(vec_blob.decode("utf-8")) if vec_blob else None
            except Exception:
                vec = None
            item = MemoryItem(id=id_, kind=kind_, text=text_, meta=json.loads(meta_json or "{}"), vector=vec)
            score = cos(qv, vec) if isinstance(vec, list) else 0.0
            scored.append((item, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
