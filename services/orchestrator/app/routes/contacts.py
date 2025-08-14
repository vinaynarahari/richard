from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import json
import re

from ..services.contacts_service import get_contacts_service, Contact

router = APIRouter(prefix="/contacts", tags=["contacts"]) 

STORE_PATH = Path(__file__).resolve().parents[2] / "data" / "contacts.json"
STORE_PATH.parent.mkdir(parents=True, exist_ok=True)


class ContactIn(BaseModel):
    name: str
    emails: Optional[List[str]] = None
    phone_numbers: Optional[List[str]] = None
    meta: Optional[Dict[str, Any]] = None


class ContactOut(BaseModel):
    name: str
    emails: List[str]
    phone_numbers: List[str]
    primary_phone: Optional[str]
    meta: Dict[str, Any] = {}


def _load_store() -> Dict[str, Any]:
    if STORE_PATH.exists():
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


def _save_store(data: Dict[str, Any]) -> None:
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_phone(p: str) -> str:
    return re.sub(r"[^0-9+]", "", p or "")


def _looks_like_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s or ""))


@router.get("/", response_model=List[ContactOut])
async def list_contacts() -> List[ContactOut]:
    store = _load_store()
    out: List[ContactOut] = []
    for name, rec in store.items():
        emails = rec.get("emails") or []
        phones = rec.get("phone_numbers") or []
        meta = rec.get("meta") or {}
        c = Contact(name=name, phone_numbers=phones, emails=emails)
        out.append(ContactOut(name=name, emails=emails, phone_numbers=phones, primary_phone=c.get_primary_phone(), meta=meta))
    return out


@router.post("/", response_model=ContactOut)
async def upsert_contact(body: ContactIn) -> ContactOut:
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="name required")
    store = _load_store()
    rec = store.get(body.name) or {}
    raw_emails = (body.emails or rec.get("emails") or [])
    emails = [e.strip() for e in raw_emails if e and _looks_like_email(e.strip())]
    phones = [_normalize_phone(p) for p in (body.phone_numbers or rec.get("phone_numbers") or []) if _normalize_phone(p)]
    meta = body.meta or rec.get("meta") or {}
    store[body.name] = {"emails": emails, "phone_numbers": phones, "meta": meta}
    _save_store(store)
    c = Contact(name=body.name, phone_numbers=phones, emails=emails)
    return ContactOut(name=body.name, emails=emails, phone_numbers=phones, primary_phone=c.get_primary_phone(), meta=meta)


@router.get("/search", response_model=List[ContactOut])
async def search_contacts(q: str = Query(..., min_length=1), max_results: int = Query(5, ge=1, le=50)) -> List[ContactOut]:
    ql = q.lower().strip()
    store = _load_store()
    matches: List[ContactOut] = []
    for name, rec in store.items():
        if ql in name.lower() or any(ql in (e or "").lower() for e in rec.get("emails", [])):
            c = Contact(name=name, phone_numbers=rec.get("phone_numbers") or [], emails=rec.get("emails") or [])
            matches.append(ContactOut(name=name, emails=c.emails, phone_numbers=c.phone_numbers, primary_phone=c.get_primary_phone(), meta=rec.get("meta") or {}))
        if len(matches) >= max_results:
            break
    if not matches:
        # Fallback to macOS contacts suggestions
        svc = get_contacts_service()
        suggestions = await svc.get_contact_suggestions(q, max_results=max_results)
        out: List[ContactOut] = []
        for s in suggestions:
            out.append(ContactOut(name=s.name, emails=s.emails, phone_numbers=s.phone_numbers, primary_phone=s.get_primary_phone(), meta={}))
        return out
    return matches[:max_results]


@router.delete("/", response_model=Dict[str, Any])
async def delete_contact(name: str) -> Dict[str, Any]:
    store = _load_store()
    if name in store:
        store.pop(name, None)
        _save_store(store)
        return {"ok": True}
    raise HTTPException(status_code=404, detail="not found") 