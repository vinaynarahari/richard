from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load .env from the orchestrator root (services/orchestrator/.env)
_env_path = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=str(_env_path), override=False)

# Existing app imports remain above; we include new routers below
from .routes.llm import router as llm_router
from .routes.memory import router as memory_router
from .routes.imessage import router as imessage_router
from .routes.oauth import router as oauth_router  # NEW
from .routes.oauth import gmail_router  # NEW: gmail draft/send endpoints
from .routes.oauth import legacy_router as oauth_legacy_router  # ensure /callback/google (no /oauth prefix) works
from .routes.calendar import router as calendar_router  # NEW
from .routes.notion import router as notion_router  # NEW
from .routes.search import router as search_router  # NEW
from .routes.contacts import router as contacts_router  # NEW

# Import voice router
from .routes.voice import router as voice_router
VOICE_ROUTER_AVAILABLE = True


def create_app() -> FastAPI:
    app = FastAPI(title="Richard Orchestrator", version=os.getenv("ORCH_VERSION", "0.1.0"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include new routes
    app.include_router(llm_router)
    app.include_router(memory_router)
    app.include_router(voice_router)
    app.include_router(imessage_router)
    app.include_router(oauth_router)  # NEW
    app.include_router(oauth_legacy_router)  # mount legacy /callback/google at root
    app.include_router(gmail_router)  # NEW: expose /gmail/* and /dev/gmail/* endpoints
    app.include_router(calendar_router)  # NEW
    app.include_router(notion_router)  # NEW
    app.include_router(search_router)  # NEW
    app.include_router(contacts_router)  # NEW

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True}

    return app


app = create_app()
