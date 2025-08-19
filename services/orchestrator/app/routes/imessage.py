from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import re as _re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, constr

from ..memory.sqlite_store import SQLiteMemory

router = APIRouter(prefix="/imessage", tags=["imessage"])
_memory = SQLiteMemory()

# Path to the Swift helper binary (debug build path)
# __file__ -> services/orchestrator/app/routes/imessage.py
# resolve().parents indices:
#   0: imessage.py
#   1: routes
#   2: app
#   3: orchestrator
#   4: services
#   5: repo root (richard)
# We want: repo root/tools/imessage-helper/.build/debug/imessage-helper
# If parents[5] does not exist (in some run contexts), fall back to computed path via services path.
# Compute helper path robustly:
# 1) Allow override via env IMESSAGE_HELPER
# 2) Try repo-root relative (…/richard/tools/imessage-helper/.build/debug/imessage-helper)
# 3) Fallback to CWD-based guess if needed
import os as _os

def _find_group_chat_with_enhanced_fuzzy_matching(group_name: str) -> Optional[Dict[str, Any]]:
    """Find group chat using enhanced fuzzy matching from mac_messages_mcp"""
    try:
        import sys
        import os
        sys.path.insert(0, '/Users/vinaynarahari/Desktop/Github/richard/mac_messages_mcp')
        from mac_messages_mcp.messages import find_group_chat_by_name
        
        print(f"[imessage.send] '{group_name}' looks like a group chat name, searching with fuzzy matching...")
        
        # Use enhanced fuzzy matching for group chats
        group_chats = find_group_chat_by_name(group_name, max_results=3)
        
        if not group_chats:
            print(f"[imessage.send] No group chat found matching '{group_name}'")
            return None
        
        if len(group_chats) == 1:
            # Single match - use it
            group_chat = group_chats[0]
            print(f"[imessage.send] Found single group chat: {group_chat['name']} ({group_chat.get('confidence', 'unknown')} confidence)")
            return group_chat
        
        # Multiple matches - choose the highest confidence one
        best_group = group_chats[0]  # Already sorted by score
        
        # If the best match has very high confidence, use it automatically
        if best_group.get('confidence') == 'very_high' or best_group.get('score', 0) >= 0.9:
            print(f"[imessage.send] Auto-selected high confidence group: {best_group['name']} ({best_group.get('confidence', 'unknown')} confidence)")
            return best_group
        
        # Otherwise, log the ambiguity but still use the best match
        print(f"[imessage.send] Multiple group chats found for '{group_name}', using best match: {best_group['name']} ({best_group.get('confidence', 'unknown')} confidence)")
        for i, group_chat in enumerate(group_chats[:3], 1):
            print(f"[imessage.send]   {i}. {group_chat['name']} - {group_chat.get('match_type', 'unknown')} match, {group_chat.get('confidence', 'unknown')} confidence")
        
        return best_group
        
    except ImportError as e:
        print(f"[imessage.send] Enhanced group chat fuzzy matching not available: {e}")
        return None
    except Exception as e:
        print(f"[imessage.send] Enhanced group chat fuzzy matching failed: {e}")
        return None

def _find_contact_with_enhanced_fuzzy_matching(contact_name: str) -> Optional[Dict[str, Any]]:
    """Find contact using enhanced fuzzy matching from mac_messages_mcp"""
    try:
        import sys
        import os
        sys.path.insert(0, '/Users/vinaynarahari/Desktop/Github/richard/mac_messages_mcp')
        from mac_messages_mcp.messages import find_contact_by_name
        
        print(f"[imessage.send] '{contact_name}' looks like a contact name, searching with fuzzy matching...")
        
        # Use enhanced fuzzy matching
        contacts = find_contact_by_name(contact_name, max_results=3)
        
        if not contacts:
            print(f"[imessage.send] No contact found matching '{contact_name}'")
            return None
        
        if len(contacts) == 1:
            # Single match - use it
            contact = contacts[0]
            print(f"[imessage.send] Found single contact: {contact['name']} ({contact.get('confidence', 'unknown')} confidence)")
            return contact
        
        # Multiple matches - choose the highest confidence one
        best_contact = contacts[0]  # Already sorted by score
        
        # If the best match has very high confidence, use it automatically
        if best_contact.get('confidence') == 'very_high' or best_contact.get('score', 0) >= 0.9:
            print(f"[imessage.send] Auto-selected high confidence match: {best_contact['name']} ({best_contact.get('confidence', 'unknown')} confidence)")
            return best_contact
        
        # Otherwise, log the ambiguity but still use the best match
        print(f"[imessage.send] Multiple contacts found for '{contact_name}', using best match: {best_contact['name']} ({best_contact.get('confidence', 'unknown')} confidence)")
        for i, contact in enumerate(contacts[:3], 1):
            print(f"[imessage.send]   {i}. {contact['name']} - {contact.get('match_type', 'unknown')} match, {contact.get('confidence', 'unknown')} confidence")
        
        return best_contact
        
    except ImportError as e:
        print(f"[imessage.send] Enhanced fuzzy matching not available: {e}")
        return None
    except Exception as e:
        print(f"[imessage.send] Enhanced fuzzy matching failed: {e}")
        return None

def _compute_helper_path() -> Path:
    env_path = _os.getenv("IMESSAGE_HELPER")
    if env_path:
        return Path(env_path)

    here = Path(__file__).resolve()
    # Expected layout: /repo/services/orchestrator/app/routes/imessage.py
    # repo root = parents[6] from file
    candidates: list[Path] = []
    try:
        repo_root = here.parents[6]
        candidates.append(repo_root / "tools" / "imessage-helper" / ".build" / "debug" / "imessage-helper")
    except Exception:
        pass

    # Also try parents[5] and parents[4] in case of different run contexts
    for i in (5, 4):
        try:
            root_i = here.parents[i]
            candidates.append(root_i / "tools" / "imessage-helper" / ".build" / "debug" / "imessage-helper")
        except Exception:
            continue

    # CWD fallback (useful if running uvicorn from repo root)
    try:
        cwd = Path.cwd()
        candidates.append(cwd / "tools" / "imessage-helper" / ".build" / "debug" / "imessage-helper")
    except Exception:
        pass

    for p in candidates:
        if p.exists() and p.is_file():
            return p

    # Last resort: return the first candidate even if missing to surface a clear error
    return candidates[0] if candidates else here

HELPER_PATH = _compute_helper_path()


class ResolveRequest(BaseModel):
    query: constr(strip_whitespace=True, min_length=1)


class ResolveResult(BaseModel):
    chat_id: str
    display_name: Optional[str] = None
    participants: List[str] = Field(default_factory=list)


class ResolveResponse(BaseModel):
    status: str
    results: List[ResolveResult] = Field(default_factory=list)


class SendByChatId(BaseModel):
    chat_id: constr(strip_whitespace=True, min_length=1)
    body: constr(strip_whitespace=True, min_length=1)


class SendByRecipients(BaseModel):
    to: List[constr(strip_whitespace=True, min_length=1)]
    body: constr(strip_whitespace=True, min_length=1)


class SendByGroup(BaseModel):
    group: constr(strip_whitespace=True, min_length=1)
    body: constr(strip_whitespace=True, min_length=1)

class SendByContact(BaseModel):
    contact: constr(strip_whitespace=True, min_length=1)
    body: constr(strip_whitespace=True, min_length=1)


SendPayload = Union[SendByGroup, SendByContact, SendByChatId, SendByRecipients]


def _ensure_helper() -> None:
    if not HELPER_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"iMessage helper not found at {HELPER_PATH}. Build it with: cd tools/imessage-helper && swift build",
        )
    if not HELPER_PATH.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"iMessage helper path is not a file: {HELPER_PATH}",
        )


def _run_helper(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_helper()
    try:
        proc = subprocess.run(
            [str(HELPER_PATH)],
            input=json.dumps(payload).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"Helper not executable: {HELPER_PATH}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to launch helper: {e}")

    out = proc.stdout.decode("utf-8", errors="ignore").strip()
    err = proc.stderr.decode("utf-8", errors="ignore").strip()

    if not out:
        raise HTTPException(status_code=500, detail=f"Empty response from helper. stderr={err}")

    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from helper: {out}")

    # Normalize common error shape
    if data.get("status") == "error":
        # Special-case multiple match scenario from helper to surface candidates upstream
        if (data.get("detail") == "multiple_matches") and data.get("to"):
            raise HTTPException(status_code=409, detail={"error": "multiple_matches", "candidates": data.get("to")})
        # General helper error: keep structure for upstream handling
        raise HTTPException(status_code=500, detail={
            "error": data.get("error") or "helper_error",
            "detail": data.get("detail") or "Unknown error",
        })

    return data


def _sanitize_query(q: str) -> str:
    # Remove most non-word characters (keeps letters/numbers/space/@.+- for emails/handles), collapse spaces
    s = _re.sub(r"[^A-Za-z0-9 @.+\-]", "", q)
    return " ".join(s.split())


def _select_preferred_handle(handles: List[str]) -> Optional[str]:
    """Pick a single best handle. Prefer phone-number-like handles, else first available.
    Accepts E.164-ish (+digits) or plain digits with length >=7.
    """
    if not handles:
        return None
    phone_like = []
    for h in handles:
        hs = (h or "").strip()
        # common encodings sometimes include spaces; strip them
        hs_compact = hs.replace(" ", "")
        if _re.match(r"^\+?\d{7,}$", hs_compact):
            phone_like.append(hs_compact)
    if phone_like:
        # Prefer those starting with '+' (E.164) if available
        e164 = [p for p in phone_like if p.startswith("+")]
        return (e164[0] if e164 else phone_like[0])
    # Fallback: first handle as-is
    return (handles[0] or "").strip()


@router.post("/resolve", response_model=ResolveResponse)
def resolve(req: ResolveRequest) -> ResolveResponse:
    payload = {"action": "resolve", "query": req.query}
    data = _run_helper(payload)
    results = data.get("results") or []
    # Validate into pydantic models
    _results: List[ResolveResult] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        _results.append(
            ResolveResult(
                chat_id=str(r.get("chat_id", "")),
                display_name=r.get("display_name"),
                participants=[str(p) for p in (r.get("participants") or [])],
            )
        )
    return ResolveResponse(status=str(data.get("status", "ok")), results=_results)


@router.post("/send")
def send(payload: SendPayload) -> Dict[str, Any]:
    # Explicit routing based on payload fields to ensure correct handling
    # This prevents Union type resolution issues in different environments
    if hasattr(payload, 'group') and getattr(payload, 'group', None):
        # Force group chat handling even if Union resolution is incorrect
        if not isinstance(payload, SendByGroup):
            payload = SendByGroup(group=payload.group, body=payload.body)
    elif hasattr(payload, 'contact') and getattr(payload, 'contact', None):
        # Force contact handling even if Union resolution is incorrect  
        if not isinstance(payload, SendByContact):
            payload = SendByContact(contact=payload.contact, body=payload.body)
    
    # Three forms: by chat_id, by recipients, or by group (server resolves then sends)
    if isinstance(payload, SendByChatId):
        req = {"action": "send", "chat_id": payload.chat_id, "body": payload.body}
        try:
            resp = _run_helper(req)
            # Save group/thread id usage
            try:
                _ = _memory.insert(
                    kind="im_group_usage",
                    text=f"chat:{payload.chat_id}",
                    meta={"channel": "imessage", "chat_id": payload.chat_id},
                    vector=None,
                )
            except Exception:
                pass
            return resp
        except HTTPException as e:
            # If helper failed due to non-scriptable chat id, try to resolve participants and send that way
            if e.status_code == 500 and "chat_id" in (e.detail or ""):
                r = _run_helper({"action": "resolve", "query": payload.chat_id})
                candidates = r.get("results") or []
                if candidates:
                    cand = candidates[0]
                    parts = cand.get("participants") or []
                    if parts:
                        # Split multi-recipient into N single-recipient sends to avoid -1728 on some macOS builds
                        results: List[Dict[str, Any]] = []
                        for p in parts:
                            try:
                                results.append(_run_helper({"action": "send", "to": [p], "body": payload.body}))
                                try:
                                    _ = _memory.insert(
                                        kind="im_handle",
                                        text=p,
                                        meta={"channel": "imessage"},
                                        vector=None,
                                    )
                                except Exception:
                                    pass
                            except HTTPException as ie:
                                results.append({"status": "error", "detail": ie.detail})
                        return {"status": "ok", "results": results}
            raise

    if isinstance(payload, SendByRecipients):
        if not payload.to:
            raise HTTPException(status_code=400, detail="Missing recipients")
        # If more than one recipient, split into single sends to avoid group AppleScript issues
        if len(payload.to) > 1:
            results: List[Dict[str, Any]] = []
            for p in payload.to:
                try:
                    res = _run_helper({"action": "send", "to": [p], "body": payload.body})
                    results.append(res)
                    try:
                        _ = _memory.insert(
                            kind="im_handle",
                            text=p,
                            meta={"channel": "imessage"},
                            vector=None,
                        )
                    except Exception:
                        pass
                except HTTPException as e:
                    results.append({"status": "error", "detail": e.detail})
            # If every attempt failed, surface error instead of silent OK
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "sent")
            if success_count == 0:
                raise HTTPException(status_code=500, detail="All recipient sends failed")
            return {"status": "ok", "results": results}
        # Single recipient path
        req = {"action": "send", "to": payload.to, "body": payload.body}
        resp = _run_helper(req)
        try:
            _ = _memory.insert(
                kind="im_handle",
                text=payload.to[0],
                meta={"channel": "imessage"},
                vector=None,
            )
        except Exception:
            pass
        return resp

    if isinstance(payload, SendByGroup):
        # 0) Try enhanced fuzzy group chat matching first
        try:
            enhanced_group = _find_group_chat_with_enhanced_fuzzy_matching(payload.group)
            if enhanced_group:
                group_name = enhanced_group['name']
                resp = _run_helper({"action": "send_by_display_name", "display_name": group_name, "body": payload.body})
                try:
                    _ = _memory.insert(
                        kind="im_group",
                        text=f"group:{payload.group}",
                        meta={
                            "channel": "imessage", 
                            "display_name": group_name,
                            "match_type": enhanced_group.get('match_type', 'fuzzy'),
                            "confidence": enhanced_group.get('confidence', 'unknown'),
                            "source": "enhanced_group_fuzzy_matching"
                        },
                        vector=None,
                    )
                except Exception:
                    pass
                return resp
        except Exception as e:
            print(f"Enhanced group fuzzy matching failed: {e}")
            pass
        
        # 1) Try direct display-name send with exact name (fallback)
        try:
            resp = _run_helper({"action": "send_by_display_name", "display_name": payload.group, "body": payload.body})
            try:
                _ = _memory.insert(
                    kind="im_group",
                    text=f"group:{payload.group}",
                    meta={"channel": "imessage", "display_name": payload.group},
                    vector=None,
                )
            except Exception:
                pass
            return resp
        except HTTPException:
            pass

        # 2) Then try DB resolver (FDA required)
        q = payload.group
        r = _run_helper({"action": "resolve", "query": q})
        candidates = r.get("results") or []
        if not candidates:
            sq = _sanitize_query(q)
            if sq and sq != q:
                r = _run_helper({"action": "resolve", "query": sq})
                candidates = r.get("results") or []
        # 3) Fallback to AppleScript fuzzy resolver
        if not candidates:
            r = _run_helper({"action": "resolve_as", "query": q})
            candidates = r.get("results") or []
            if not candidates and sq and sq != q:
                r = _run_helper({"action": "resolve_as", "query": sq})
                candidates = r.get("results") or []
        if not candidates:
            raise HTTPException(status_code=404, detail=f'Group "{payload.group}" not found')

        cand = candidates[0]
        chat_id = cand.get("chat_id")
        display_name = cand.get("display_name") or payload.group

        # 4) Prefer sending by display name when available (use resolved display name)
        try:
            resp = _run_helper({"action": "send_by_display_name", "display_name": display_name, "body": payload.body})
            return resp
        except HTTPException:
            pass

        # 5) If chat id is scriptable, try it
        if isinstance(chat_id, str) and (";-;" in chat_id):
            try:
                return _run_helper({"action": "send", "chat_id": chat_id, "body": payload.body})
            except HTTPException:
                pass

        # Strict mode: do not fall back to individual participants for group sends
        raise HTTPException(status_code=404, detail=f'Group "{payload.group}" not found')

    if isinstance(payload, SendByContact):
        # 0a) Try Contacts app lookup for handles (phones/emails) and pick a preferred handle first
        try:
            data = _run_helper({"action": "lookup_contact_handles", "contact": payload.contact, "body": payload.body})
            handles = [str(h) for h in (data.get("handles") or [])]
            preferred = _select_preferred_handle(handles)
            if preferred:
                try:
                    resp = _run_helper({"action": "send", "to": [preferred], "body": payload.body})
                    try:
                        _ = _memory.insert(
                            kind="im_contact",
                            text=f"contact:{payload.contact}",
                            meta={"channel": "imessage", "name": payload.contact, "handle": preferred},
                            vector=None,
                        )
                    except Exception:
                        pass
                    return resp
                except HTTPException:
                    pass
        except Exception:
            pass

        # 0) Try enhanced fuzzy matching (contacts and group chats)
        try:
            # First check if this might be a group chat (multi-word names often are)
            if len(payload.contact.split()) > 1:
                enhanced_group = _find_group_chat_with_enhanced_fuzzy_matching(payload.contact)
                if enhanced_group and enhanced_group.get('confidence') in ['very_high', 'high']:
                    # Only auto-select group if high confidence to avoid wrong selections
                    room_id = enhanced_group.get('room_id')
                    if room_id:
                        resp = _run_helper({"action": "send_by_display_name", "display_name": enhanced_group['name'], "body": payload.body})
                        try:
                            _ = _memory.insert(
                                kind="im_contact",
                                text=f"group:{payload.contact}",
                                meta={
                                    "channel": "imessage", 
                                    "name": enhanced_group['name'],
                                    "room_id": room_id,
                                    "match_type": enhanced_group.get('match_type', 'fuzzy'),
                                    "confidence": enhanced_group.get('confidence', 'unknown'),
                                    "source": "enhanced_group_fuzzy_matching",
                                    "type": "group_chat"
                                },
                                vector=None,
                            )
                        except Exception:
                            pass
                        return resp
            
            # Try individual contact matching
            enhanced_contact = _find_contact_with_enhanced_fuzzy_matching(payload.contact)
            if enhanced_contact:
                phone = enhanced_contact.get('phone')
                if phone:
                    resp = _run_helper({"action": "send", "to": [phone], "body": payload.body})
                    try:
                        _ = _memory.insert(
                            kind="im_contact",
                            text=f"contact:{payload.contact}",
                            meta={
                                "channel": "imessage", 
                                "name": enhanced_contact['name'],
                                "handle": phone,
                                "match_type": enhanced_contact.get('match_type', 'fuzzy'),
                                "confidence": enhanced_contact.get('confidence', 'unknown'),
                                "source": "enhanced_fuzzy_matching"
                            },
                            vector=None,
                        )
                    except Exception:
                        pass
                    return resp
            
            # If no good individual contact found, try group chats with lower confidence
            enhanced_group = _find_group_chat_with_enhanced_fuzzy_matching(payload.contact)
            if enhanced_group:
                room_id = enhanced_group.get('room_id')
                if room_id:
                    print(f"[imessage.send] No individual contact found, trying group chat: {enhanced_group['name']} ({enhanced_group.get('confidence', 'unknown')} confidence)")
                    resp = _run_helper({"action": "send_by_display_name", "display_name": enhanced_group['name'], "body": payload.body})
                    try:
                        _ = _memory.insert(
                            kind="im_contact",
                            text=f"group:{payload.contact}",
                            meta={
                                "channel": "imessage", 
                                "name": enhanced_group['name'],
                                "room_id": room_id,
                                "match_type": enhanced_group.get('match_type', 'fuzzy'),
                                "confidence": enhanced_group.get('confidence', 'unknown'),
                                "source": "enhanced_group_fuzzy_matching_fallback",
                                "type": "group_chat"
                            },
                            vector=None,
                        )
                    except Exception:
                        pass
                    return resp
        except Exception as e:
            print(f"Enhanced fuzzy matching failed: {e}")
            pass
        
        # 1) Prefer buddy-id path (reliable for 1:1): find by display name -> sendToBuddyId
        try:
            data = _run_helper({"action": "send_by_contact_name", "contact": payload.contact, "body": payload.body})
            try:
                _ = _memory.insert(
                    kind="im_contact",
                    text=f"contact:{payload.contact}",
                    meta={"channel": "imessage", "name": payload.contact},
                    vector=None,
                )
            except Exception:
                pass
            return data
        except HTTPException as e:
            # If multiple matches, try to auto-pick a preferred handle from candidates instead of aborting
            try:
                detail = getattr(e, "detail", None)
                if isinstance(detail, dict) and detail.get("candidates"):
                    candidates = [str(c) for c in (detail.get("candidates") or [])]
                    preferred = _select_preferred_handle(candidates)
                    if preferred:
                        try:
                            resp = _run_helper({"action": "send", "to": [preferred], "body": payload.body})
                            try:
                                _ = _memory.insert(
                                    kind="im_contact",
                                    text=f"contact:{payload.contact}",
                                    meta={"channel": "imessage", "name": payload.contact, "handle": preferred},
                                    vector=None,
                                )
                            except Exception:
                                pass
                            return resp
                        except HTTPException:
                            pass
            except Exception:
                pass
            # Fall through to other strategies

        # 2) Try direct display-name send (restores legacy behavior that worked for some 1:1 threads)
        try:
            data = _run_helper({"action": "send_by_display_name", "display_name": payload.contact, "body": payload.body})
            try:
                _ = _memory.insert(
                    kind="im_contact",
                    text=f"contact:{payload.contact}",
                    meta={"channel": "imessage", "name": payload.contact},
                    vector=None,
                )
            except Exception:
                pass
            return data
        except HTTPException:
            pass

        # 3) Resolve candidates and choose a single preferred handle (phone) to send directly
        q = payload.contact
        r = _run_helper({"action": "resolve", "query": q})
        candidates = r.get("results") or []
        if not candidates:
            sq = _sanitize_query(q)
            if sq and sq != q:
                r = _run_helper({"action": "resolve", "query": sq})
                candidates = r.get("results") or []
        if not candidates:
            r = _run_helper({"action": "resolve_as", "query": q})
            candidates = r.get("results") or []
            if not candidates and sq and sq != q:
                r = _run_helper({"action": "resolve_as", "query": sq})
                candidates = r.get("results") or []
        if candidates:
            # Prefer a 1:1 candidate (single participant) if available
            cand: Dict[str, Any] = next((c for c in candidates if len(c.get("participants") or []) == 1), candidates[0])
            parts = cand.get("participants") or []
            preferred = _select_preferred_handle([str(p) for p in parts])
            if preferred:
                try:
                    resp = _run_helper({"action": "send", "to": [preferred], "body": payload.body})
                    try:
                        _ = _memory.insert(
                            kind="im_contact",
                            text=f"contact:{payload.contact}",
                            meta={"channel": "imessage", "name": payload.contact, "handle": preferred},
                            vector=None,
                        )
                    except Exception:
                        pass
                    return resp
                except HTTPException:
                    pass
            # Fallback: attempt each participant and aggregate
            results: List[Dict[str, Any]] = []
            for p in parts:
                try:
                    results.append(_run_helper({"action": "send", "to": [p], "body": payload.body}))
                except HTTPException as e:
                    results.append({"status": "error", "detail": e.detail})
            # If every attempt failed, surface error instead of silent OK
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "sent")
            if success_count == 0:
                # As a last resort try chat-id path before giving up
                chat_id = cand.get("chat_id")
                if isinstance(chat_id, str):
                    try:
                        return _run_helper({"action": "send", "chat_id": chat_id, "body": payload.body})
                    except HTTPException:
                        pass
                raise HTTPException(status_code=404, detail=f'Contact "{payload.contact}" not reachable')
            return {"status": "ok", "results": results}
        # No valid path
        raise HTTPException(status_code=404, detail=f'Contact "{payload.contact}" not found')

    raise HTTPException(status_code=400, detail="Unsupported payload")
