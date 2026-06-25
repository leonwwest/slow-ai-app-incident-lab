from fastapi import APIRouter

from app.routers import chat, diagnostics, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(diagnostics.router)
