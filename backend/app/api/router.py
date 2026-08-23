from fastapi import APIRouter

from app.api.routes import (
    analysis,
    companies,
    data_management,
    evidence,
    fx_rates,
    health,
    investment_tools,
    market_data,
    memos,
    parameter_config,
    price_decisions,
    system_control,
    valuations,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(system_control.router, tags=["system"])
api_router.include_router(companies.router, tags=["companies"])
api_router.include_router(market_data.router, tags=["market-data"])
api_router.include_router(fx_rates.router, tags=["market-data"])
api_router.include_router(investment_tools.router, tags=["investment-tools"])
api_router.include_router(evidence.router, tags=["evidence"])
api_router.include_router(analysis.router, tags=["analysis"])
api_router.include_router(memos.router, tags=["memos"])
api_router.include_router(valuations.router, tags=["valuations"])
api_router.include_router(price_decisions.router, tags=["price-decisions"])
api_router.include_router(parameter_config.router, tags=["parameter-config"])
api_router.include_router(data_management.router, tags=["data-management"])
