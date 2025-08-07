from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..llm.ollama_client import OllamaClient


DEFAULT_DB_PATH = Path(os.getenv("MEMORY_DB_PATH", "app/memory.db")).resolve()
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


@dataclass
class MemoryItem:
    id: Optional[int]
    kind: str
    text: str
    meta: Dict[str, Any]
    vector: Optional[List[float]]


class SQLiteMemory:
    """
    Simple SQLite-backed memory store with cosine similarity search over Ollama embeddings.
    """

    def __init__(self, db_path: Path = DEFAULT_DB_PATH, ollama: Optional[OllamaClient] = None):
        self.db_path = db_path
        self.ollama = ollama or OllamaClient(base_url=OLLAMA_BASE)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    meta TEXT,
                    vector BLOB
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind)")
            con.commit()

    @staticmethod
    def _to_blob(vec: Optional[List[float]]) -> Optional[bytes]:
        if vec is None:
            return None
        return json.dumps(vec).encode("utf-8")

    @staticmethod
    def _from_blob(blob: Optional[bytes]) -> Optional[List[float]]:
        if blob is None:
            return None
        return json.loads(blob.decode("utf-8"))

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        return await self.ollama.embeddings(EMBED_MODEL, texts)  # type: ignore[arg-type]

    def insert(self, kind: str, text: str, meta: Optional[Dict[str, Any]] = None, vector: Optional[List[float]] = None) -> int:
        with self._connect() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO memories(kind, text, meta, vector) VALUES (?, ?, ?, ?)",
                (kind, text, json.dumps(meta or {}), self._to_blob(vector)),
            )
            con.commit()
            return int(cur.lastrowid)

    async def insert_with_embedding(self, kind: str, text: str, meta: Optional[Dict[str, Any]] = None) -> int:
        vectors = await self.embed_texts([text])
        return self.insert(kind, text, meta, vectors[0])

    def all(self) -> List[MemoryItem]:
        with self._connect() as con:
            rows = con.execute("SELECT id, kind, text, meta, vector FROM memories").fetchall()
        items: List[MemoryItem] = []
        for r in rows:
            items.append(
                MemoryItem(
                    id=r["id"],
                    kind=r["kind"],
                    text=r["text"],
                    meta=json.loads(r["meta"] or "{}"),
                    vector=self._from_blob(r["vector"]),
                )
            )
        return items

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        import math

        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    async def search(self, query: str, top_k: int = 5, kind: Optional[str] = None) -> List[Tuple[MemoryItem, float]]:
        qv = (await self.embed_texts([query]))[0]
        with self._connect() as con:
            rows = con.execute("SELECT id, kind, text, meta, vector FROM memories" + ("" if not kind else " WHERE kind=?"),
                               (() if not kind else (kind,))).fetchall()
        scored: List[Tuple[MemoryItem, float]] = []
        for r in rows:
            item = MemoryItem(
                id=r["id"],
                kind=r["kind"],
                text=r["text"],
                meta=json.loads(r["meta"] or "{}"),
                vector=self._from_blob(r["vector"]),
            )
            if item.vector is None:
                continue
            score = self._cosine(qv, item.vector)
            scored.append((item, score))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_k]

    def close(self) -> None:
        # httpx session is owned by OllamaClient; let orchestrator lifespan close if needed.
        pass
