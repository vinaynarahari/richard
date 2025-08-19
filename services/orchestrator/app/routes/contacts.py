from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
import json
import re
import difflib
# Using difflib instead of fuzzywuzzy for better compatibility
import difflib
# Using difflib instead of fuzzywuzzy for compatibility

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


def _calculate_similarity_score(query: str, name: str) -> float:
    """Calculate similarity score between query and contact name using multiple methods."""
    query_lower = query.lower().strip()
    name_lower = name.lower().strip()
    
    # If exact match or exact substring, give highest score
    if query_lower == name_lower:
        return 1.0
    if query_lower in name_lower or name_lower in query_lower:
        return 0.95
    
    # Use difflib for fuzzy matching (built-in, no dependencies)
    ratio = difflib.SequenceMatcher(None, query_lower, name_lower).ratio()
    # Simulate partial ratio by checking substrings
    partial_ratio = max(
        difflib.SequenceMatcher(None, query_lower, name_lower).ratio(),
        difflib.SequenceMatcher(None, query_lower, name_lower[:len(query_lower)]).ratio() if len(name_lower) >= len(query_lower) else 0,
        difflib.SequenceMatcher(None, query_lower, name_lower[-len(query_lower):]).ratio() if len(name_lower) >= len(query_lower) else 0
    )
    # For token matching, split into words and compare
    query_words = query_lower.split()
    name_words = name_lower.split()
    token_sort_ratio = difflib.SequenceMatcher(None, ' '.join(sorted(query_words)), ' '.join(sorted(name_words))).ratio()
    token_set_ratio = len(set(query_words) & set(name_words)) / max(len(set(query_words) | set(name_words)), 1)
    
    # Weight different matching methods
    score = (
        ratio * 0.3 +
        partial_ratio * 0.25 +
        token_sort_ratio * 0.25 +
        token_set_ratio * 0.2
    )
    
    # Bonus for name starting with query (common when typing names)
    if name_lower.startswith(query_lower):
        score += 0.1
    
    # Bonus for matching first letters of words (e.g., "JD" matches "John Doe")
    name_initials = ''.join([word[0] for word in name_lower.split() if word])
    if query_lower == name_initials:
        score += 0.15
    
    return min(score, 1.0)


def _find_best_contact_matches(query: str, contacts: Dict[str, Any], max_results: int = 5, min_score: float = 0.3) -> List[Tuple[str, Dict[str, Any], float]]:
    """Find best matching contacts with fuzzy search and similarity scoring."""
    matches = []
    
    for name, contact_data in contacts.items():
        # Calculate similarity score for the name
        score = _calculate_similarity_score(query, name)
        
        # Also check email addresses for matches
        emails = contact_data.get("emails", [])
        for email in emails:
            if email and query.lower() in email.lower():
                score = max(score, 0.8)  # High score for email matches
        
        # Also check phone numbers (for partial matches)
        phones = contact_data.get("phone_numbers", [])
        for phone in phones:
            if phone and query in _normalize_phone(phone):
                score = max(score, 0.9)  # Very high score for phone matches
        
        if score >= min_score:
            matches.append((name, contact_data, score))
    
    # Sort by score descending
    matches.sort(key=lambda x: x[2], reverse=True)
    return matches[:max_results]


def _suggest_similar_names(query: str, contacts: Dict[str, Any], max_suggestions: int = 3) -> List[str]:
    """Generate suggestions for similar contact names when no good matches found."""
    all_names = list(contacts.keys())
    if not all_names:
        return []
    
    # Use difflib to find close matches
    close_matches = difflib.get_close_matches(query, all_names, n=max_suggestions, cutoff=0.4)
    
    # Use difflib for additional fuzzy suggestions
    fuzzy_names = []
    for name in all_names:
        if name not in close_matches:
            similarity = difflib.SequenceMatcher(None, query.lower(), name.lower()).ratio()
            if similarity >= 0.4:  # 40% similarity threshold
                fuzzy_names.append(name)
    
    # Combine and deduplicate
    suggestions = list(dict.fromkeys(close_matches + fuzzy_names))
    return suggestions[:max_suggestions]


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
    """Smart contact search with fuzzy matching, spell correction, and similarity scoring."""
    query = q.strip()
    
    # Priority 1: Try mac_messages_mcp enhanced fuzzy matching (most accurate!)
    try:
        print(f"Attempting enhanced fuzzy search for query: '{query}'")
        # Import the enhanced fuzzy matching from mac_messages_mcp
        import sys
        sys.path.insert(0, '/Users/vinaynarahari/Desktop/Github/richard/mac_messages_mcp')
        from mac_messages_mcp.messages import find_contact_by_name
        
        # Use the enhanced fuzzy matching
        enhanced_contacts = find_contact_by_name(query, max_results=max_results)
        
        if enhanced_contacts:
            print(f"Enhanced fuzzy matching found {len(enhanced_contacts)} contacts")
            for i, contact in enumerate(enhanced_contacts, 1):
                print(f"  {i}. {contact['name']} ({contact.get('phone', 'N/A')}) - {contact.get('match_type', 'unknown')} match, {contact.get('confidence', 'unknown')} confidence, score: {contact.get('score', 0):.3f}")
            
            result_contacts = []
            for contact in enhanced_contacts:
                contact_out = ContactOut(
                    name=contact['name'],
                    emails=[],  # Enhanced system focuses on phone numbers
                    phone_numbers=[contact.get('phone', '')] if contact.get('phone') else [],
                    primary_phone=contact.get('phone'),
                    meta={
                        "similarity_score": round(contact.get('score', 0), 3),
                        "confidence": contact.get('confidence', 'unknown'),
                        "match_type": contact.get('match_type', 'fuzzy'),
                        "source": "enhanced_mac_messages_mcp"
                    }
                )
                result_contacts.append(contact_out)
            return result_contacts
        else:
            print(f"Enhanced fuzzy matching found no contacts for '{query}'")
            
    except ImportError as e:
        print(f"Enhanced fuzzy matching not available: {e}")
    except Exception as e:
        print(f"Enhanced fuzzy matching failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Priority 2: Try macOS contacts with fuzzy matching (fallback)
    try:
        svc = get_contacts_service()
        
        # Get contacts with enhanced suggestions
        print(f"Attempting to retrieve contacts from macOS for query: '{query}'")
        contacts_query = await svc.get_contact_suggestions(query, max_results=max_results)
        
        if contacts_query:
            print(f"Found {len(contacts_query)} contacts with enhanced suggestions")
            # Convert to our format
            result_contacts = []
            for contact in contacts_query:
                if contact.name:
                    # Calculate a simple similarity score
    
                    query_lower = query.lower()
                    name_lower = contact.name.lower()
                    
                    if query_lower == name_lower:
                        score = 1.0
                        match_type = "exact"
                    elif query_lower in name_lower:
                        score = len(query_lower) / len(name_lower) * 0.9
                        match_type = "partial"
                    else:
                        import difflib
                        score = difflib.SequenceMatcher(None, query_lower, name_lower).ratio() * 0.7
                        match_type = "fuzzy"
                    
                    confidence = "high" if score >= 0.7 else "medium" if score >= 0.5 else "low"
                    
                    contact_out = ContactOut(
                        name=contact.name,
                        emails=contact.emails,
                        phone_numbers=contact.phone_numbers,
                        primary_phone=contact.get_primary_phone(),
                        meta={
                            "similarity_score": round(score, 3),
                            "confidence": confidence,
                            "match_type": match_type,
                            "source": "macos_contacts_enhanced"
                        }
                    )
                    result_contacts.append(contact_out)
            
            if result_contacts:
                # Sort by similarity score
                result_contacts.sort(key=lambda x: x.meta.get("similarity_score", 0), reverse=True)
                return result_contacts[:max_results]
        
    except Exception as e:
        print(f"Enhanced macOS contacts search failed: {e}")
    
    # Priority 3: Try stored contacts as fallback
    store = _load_store()
    matches = _find_best_contact_matches(query, store, max_results, min_score=0.3)
    
    result_contacts = []
    for name, contact_data, score in matches:
        c = Contact(name=name, phone_numbers=contact_data.get("phone_numbers") or [], emails=contact_data.get("emails") or [])
        contact_out = ContactOut(
            name=name, 
            emails=c.emails, 
            phone_numbers=c.phone_numbers, 
            primary_phone=c.get_primary_phone(), 
            meta=contact_data.get("meta", {})
        )
        # Add similarity score to meta for debugging
        contact_out.meta["similarity_score"] = round(score, 3)
        contact_out.meta["source"] = "stored_contacts"
        result_contacts.append(contact_out)
    
    # If we found stored matches, return them
    if result_contacts:
        return result_contacts
    
    # Priority 4: Last resort - try original suggestion approach with longer timeout
    try:
        svc = get_contacts_service()
        suggestions = await svc.get_contact_suggestions(query, max_results=max_results)
        if suggestions:
            out: List[ContactOut] = []
            for s in suggestions:
                out.append(ContactOut(
                    name=s.name, 
                    emails=s.emails, 
                    phone_numbers=s.phone_numbers, 
                    primary_phone=s.get_primary_phone(), 
                    meta={"source": "system_contacts_final_fallback"}
                ))
            return out
            
    except Exception as e:
        print(f"System contacts final fallback failed: {e}")
    
    # Fallback: Provide helpful suggestions
    print(f"No contacts found for '{query}' in any method")
    suggestion_contact = ContactOut(
        name=f"No contacts found for '{query}'",
        emails=[],
        phone_numbers=[],
        primary_phone=None,
        meta={
            "type": "no_results",
            "message": f"No contacts found matching '{query}'. Try using full names, partial names, or check spelling.",
            "suggestions": [
                "Use full name (e.g., 'John Smith')",
                "Try first name only (e.g., 'John')", 
                "Check spelling",
                "Use initials (e.g., 'JS')"
            ],
            "query_attempted": query
        }
    )
    return [suggestion_contact]


@router.delete("/", response_model=Dict[str, Any])
async def delete_contact(name: str) -> Dict[str, Any]:
    store = _load_store()
    if name in store:
        store.pop(name, None)
        _save_store(store)
        return {"ok": True}
    raise HTTPException(status_code=404, detail="not found") 