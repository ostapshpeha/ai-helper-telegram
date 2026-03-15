from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.mini_app import router as mini_app_router
from app.core.database import init_db

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Honda AI Assistant",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(mini_app_router)
app.mount("/mini-app", StaticFiles(directory="mini_app", html=True), name="mini_app")


@app.get("/health")
async def health_check():
    return {"status": "ok", "message": "Honda API is running"}
