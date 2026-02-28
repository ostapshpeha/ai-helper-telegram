from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    print("🛑Server stopped")

app = FastAPI(title="Honda AI Assistant", lifespan=lifespan, docs_url=None, redoc_url=None)

@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Honda API is running"}