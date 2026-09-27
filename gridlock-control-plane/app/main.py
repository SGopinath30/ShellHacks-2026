from __future__ import annotations

import hmac
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import matches, projects, sources
from app.challenge.routes import router as challenge_router
from app.challenge.repository import health as challenge_health
from fastapi.responses import JSONResponse

app = FastAPI(
    title="SYNCHRO — Deterministic Opportunities",
    description="Deterministic spatial + temporal coordination engine. "
    "LLMs extract and assist; this service decides.",
    version="0.9.0",
)

# Wide-open CORS for hackathon demo purposes. Tighten before anything real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def require_write_key(request, call_next):
    """Protect public write routes when WRITE_API_KEY is configured."""
    key = os.getenv("WRITE_API_KEY")
    if key and request.method not in {"GET", "HEAD", "OPTIONS"}:
        supplied = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(supplied, key):
            return JSONResponse({"detail": "Invalid or missing X-API-Key"}, status_code=401)
    return await call_next(request)


app.include_router(sources.router)
app.include_router(projects.router)
app.include_router(matches.router)
app.include_router(challenge_router)


@app.get("/health")
def health():
    result = challenge_health()
    return JSONResponse(result, status_code=200 if result["status"] == "ok" else 503)
