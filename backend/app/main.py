from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, v1
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import REQUEST_ID_HEADER, CorrelationIdMiddleware, SecureHeadersMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="CareerPilot AI API", version="0.1.0")
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)

    # The last one added runs first, so secure headers also cover correlation-ID error responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(SecureHeadersMiddleware, enable_hsts=settings.app_env == "production")
    return app
