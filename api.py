from fastapi import FastAPI

app = FastAPI(
    title="Fihcoin API",
    description="Backend API for the Fihcoin economy.",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "Fihcoin API", "status": "online"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}
