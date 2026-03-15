from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.mini_app import router as mini_app_router
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    print("🛑 Server stopped")


app = FastAPI(
    title="Honda AI Assistant",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)

app.include_router(mini_app_router)
app.mount("/mini-app", StaticFiles(directory="mini_app", html=True), name="mini_app")


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Honda API is running"}
