from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from ..memory.sqlite_store import SQLiteMemory

router = APIRouter(prefix="/memory", tags=["memory"])

_memory = SQLiteMemory()


@router.post("/insert")
async def insert_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Body:
      {
        "kind": "fact|pref|note|...",
        "text": "Some memory text",
        "meta": {...},           // optional metadata
        "embed": true            // default true; if false, store without vector
      }
    """
    kind = payload.get("kind") or "fact"
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    meta = payload.get("meta") or {}
    embed = payload.get("embed", True)

    if embed:
        mem_id = await _memory.insert_with_embedding(kind=kind, text=text, meta=meta)
    else:
        mem_id = _memory.insert(kind=kind, text=text, meta=meta, vector=None)

    return {"id": mem_id, "ok": True}


@router.get("/search")
async def search_memory(
    q: str = Query(..., description="Query string"),
    top_k: int = Query(5, ge=1, le=50),
    kind: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """
    Returns top_k results with cosine similarity score.
    """
    results = await _memory.search(q, top_k=top_k, kind=kind)
    items: List[Dict[str, Any]] = []
    for item, score in results:
        items.append(
            {
                "id": item.id,
                "kind": item.kind,
                "text": item.text,
                "meta": item.meta,
                "score": score,
            }
        )
    return {"query": q, "results": items}
