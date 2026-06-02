import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.bootstrap.database import initialize_databases
from app.bootstrap.lifespan import build_lifespan
from app.bootstrap.logging import configure_sensitive_log_filter
from app.bootstrap.middleware import configure_middlewares
from app.bootstrap.routes import register_routes, register_static_assets
from app.bootstrap.runtime import (
    clear_system_sessions,
    ensure_runtime_directories,
    patch_sqlite_connect,
)
from app.core.config import PORT
from app.core.rate_limiter import initialize_trusted_proxies, start_cleanup_timer
from app.shared.version import APP_VERSION

REQUEST_PORT = int(os.getenv("REQUEST_PORT", "10308"))


def prepare_runtime() -> None:
    configure_sensitive_log_filter()
    initialize_trusted_proxies()
    start_cleanup_timer()
    patch_sqlite_connect()
    print("[🔧 SQLite] 已启用 WAL 模式 + 30秒超时（解决 database is locked）")

    ensure_runtime_directories()
    clear_system_sessions()

    try:
        from app.core.security_check import run_security_checks

        run_security_checks()
    except Exception as e:
        print(f"[🔒 安全] 安全检查失败: {e}")

    initialize_databases()


def create_app() -> FastAPI:
    prepare_runtime()
    app = FastAPI(
        lifespan=build_lifespan(REQUEST_PORT),
        docs_url=None,
        redoc_url=None,
    )
    configure_exception_handlers(app)
    configure_middlewares(app)
    register_static_assets(app)
    register_routes(app)
    return app


def configure_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception):
        if isinstance(exc, StarletteHTTPException):
            raise exc

        import logging
        import traceback
        import uuid

        request_id = uuid.uuid4().hex[:12]
        logging.getLogger("app.unhandled").error(
            f"[未捕获异常] request_id={request_id} path={request.url.path} "
            f"method={request.method}\n{traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "request_id": request_id},
        )


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
