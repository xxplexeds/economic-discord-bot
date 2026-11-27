from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, status

from database import (
    check_database_connection,
    close_database,
    initialize_database,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fihcoin.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    await initialize_database()
    yield
    await close_database()


app = FastAPI(
    title="Fihcoin API",
    description="Backend API for the Fihcoin economy.",
    version="0.2.0",
    lifespan=lifespan,
)


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
