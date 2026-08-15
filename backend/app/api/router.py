from fastapi import APIRouter

from app.api.routes import analysis, companies, evidence, health, memos, valuations

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(evidence.router, tags=["evidence"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(memos.router, tags=["memos"])
api_router.include_router(valuations.router, tags=["valuations"])
