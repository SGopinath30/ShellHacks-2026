from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import matches, projects, sources

app = FastAPI(
    title="GridLock — Control Plane",
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

app.include_router(sources.router)
app.include_router(projects.router)
app.include_router(matches.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "gridlock-control-plane"}
