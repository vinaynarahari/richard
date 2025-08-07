from __future__ import annotations

import io
import json
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

OLLAMA_BASE = "http://127.0.0.1:11434"
WHISPER_MODEL = "ZimaBlueAI/whisper-large-v3:latest"

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(..., description="16kHz mono PCM WAV recommended"),
    language: Optional[str] = Form(None, description="Language hint, e.g. 'en'. Default: auto"),
    model: Optional[str] = Form(None, description="Override Ollama whisper model id"),
) -> Dict[str, Any]:
    """
    Forwards audio to Ollama's /api/transcriptions with your Whisper model.
    Returns: {"text": "...", "language": "..."} (language if provided by backend).
    """
    model_id = model or WHISPER_MODEL

    # Read bytes
    data = await file.read()
    # Ollama's transcribe endpoint expects multipart/form-data with 'file'
    url = f"{OLLAMA_BASE}/api/transcriptions"

    form_data = {
        # Some Ollama builds accept 'model' and 'options' fields
        "model": model_id,
    }
    if language:
        # Depending on server, 'language' may be top-level or inside 'options'
        form_data["language"] = language

    files = {
        "file": (file.filename or "audio.wav", data, file.content_type or "audio/wav"),
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(url, data=form_data, files=files)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            # Return any server error text
            detail = e.response.text if hasattr(e, "response") and e.response is not None else str(e)
            raise HTTPException(status_code=502, detail=f"Ollama transcription error: {detail}")

    try:
        payload = resp.json()
    except Exception:
        # Some builds may return plain text
        payload = {"text": resp.text}

    # Normalize a few possible shapes into {"text": "..."}
    if isinstance(payload, dict):
        if "text" in payload:
            return {"text": payload.get("text"), "language": payload.get("language")}
        # Whisper-like shape
        if "segments" in payload and isinstance(payload["segments"], list):
            text = " ".join(seg.get("text", "") for seg in payload["segments"])
            return {"text": text.strip(), "language": payload.get("language")}
        # Fallback to stringified
        return {"text": json.dumps(payload, ensure_ascii=False)}
    return {"text": str(payload)}
