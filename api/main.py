import logging

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader

from config import settings
from routes import jobs_router, publish_router, sites_router, work_router

logging.basicConfig(level=settings.log_level)

app = FastAPI(
    title="Affiliate Pipeline API",
    description="Stateless REST API for agentic affiliate article generation pipeline.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# --- Auth ---

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(api_key_header)) -> str:
    if key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return key


# --- Routes ---

app.include_router(work_router,    prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(jobs_router,    prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(publish_router, prefix="/api/v1", dependencies=[Depends(require_api_key)])
app.include_router(sites_router,   prefix="/api/v1", dependencies=[Depends(require_api_key)])


@app.get("/health")
async def health() -> dict:
    """Public health check - no auth required."""
    return {"status": "ok"}
