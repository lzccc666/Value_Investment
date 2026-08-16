from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import engine
from app.services.backup_service import AutomaticBackupScheduler
from app.services.maintenance_gate import maintenance_gate


def create_app(*, initialize_database: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        scheduler: AutomaticBackupScheduler | None = None
        if initialize_database:
            init_db()
            scheduler = AutomaticBackupScheduler(engine)
            scheduler.start()
        try:
            yield
        finally:
            if scheduler:
                scheduler.stop()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    @app.middleware("http")
    async def reject_writes_during_maintenance(request, call_next):
        is_write = request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
        is_management = request.url.path.startswith(f"{settings.api_prefix}/data-management")
        if not is_write or is_management:
            return await call_next(request)
        if not maintenance_gate.begin_write():
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=503,
                content={
                    "detail": "数据库正在维护，新的写请求已暂停。",
                    "operation": maintenance_gate.operation,
                },
            )
        try:
            return await call_next(request)
        finally:
            maintenance_gate.end_write()

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "docs_url": "/docs",
            "health_url": f"{settings.api_prefix}/health",
        }

    return app


app = create_app()
