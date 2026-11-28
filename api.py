from contextlib import asynccontextmanager
import logging
import os

import aiohttp
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from database import (
    check_database_connection,
    close_database,
    initialize_database,
)
from dashboard import router as dashboard_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fihcoin.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_database()
    http_session = aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=10)
    )
    app.state.http_session = http_session
    try:
        yield
    finally:
        await http_session.close()
        await close_database()


app = FastAPI(
    title="Fihcoin API",
    description="Backend API for the Fihcoin economy.",
    version="0.2.0",
    lifespan=lifespan,
)

frontend_url = os.getenv("DASHBOARD_FRONTEND_URL", "").strip()
if frontend_url:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_url.rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )

app.include_router(dashboard_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "Fihcoin API", "status": "online"}


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        await check_database_connection()
    except Exception:
        logger.exception("PostgreSQL health check failed.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unhealthy", "database": "disconnected"},
        )

    return {"status": "healthy", "database": "connected"}
