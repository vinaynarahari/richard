from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, constr

router = APIRouter(prefix="/imessage", tags=["imessage"])

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


SendPayload = Union[SendByChatId, SendByRecipients, SendByGroup]


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
        detail = data.get("error") or data.get("detail") or "Unknown error"
        raise HTTPException(status_code=500, detail=f"Helper error: {detail}")

    return data


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
    # Three forms: by chat_id, by recipients, or by group (server resolves then sends)
    if isinstance(payload, SendByChatId):
        req = {"action": "send", "chat_id": payload.chat_id, "body": payload.body}
        try:
            return _run_helper(req)
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
                    results.append(_run_helper({"action": "send", "to": [p], "body": payload.body}))
                except HTTPException as e:
                    results.append({"status": "error", "detail": e.detail})
            return {"status": "ok", "results": results}
        # Single recipient path
        req = {"action": "send", "to": payload.to, "body": payload.body}
        return _run_helper(req)

    if isinstance(payload, SendByGroup):
        # Resolve group -> candidates
        r = _run_helper({"action": "resolve", "query": payload.group})
        candidates = r.get("results") or []
        if not candidates:
            raise HTTPException(status_code=404, detail=f'Group "{payload.group}" not found')
        cand = candidates[0]
        chat_id = cand.get("chat_id")
        participants = cand.get("participants") or []

        # If we have a scriptable chat id "*;-;*", try that first; else fall back to participants
        if isinstance(chat_id, str) and (";-;" in chat_id):
            try:
                return _run_helper({"action": "send", "chat_id": chat_id, "body": payload.body})
            except HTTPException:
                # Continue to participants fallback below
                pass

        if participants:
            # Split into single-recipient sends to ensure delivery on restricted builds
            results: List[Dict[str, Any]] = []
            for p in participants:
                try:
                    results.append(_run_helper({"action": "send", "to": [p], "body": payload.body}))
                except HTTPException as e:
                    results.append({"status": "error", "detail": e.detail})
            return {"status": "ok", "results": results}

        # If no participants, try chat_id path anyway (may work on some builds)
        if chat_id:
            return _run_helper({"action": "send", "chat_id": chat_id, "body": payload.body})

        raise HTTPException(status_code=500, detail="Resolver returned neither participants nor usable chat_id")

    raise HTTPException(status_code=400, detail="Unsupported payload")
