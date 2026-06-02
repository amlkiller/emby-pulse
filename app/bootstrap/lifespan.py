from contextlib import asynccontextmanager

from .services import get_bootstrap_registry, stop_bootstrap_services


def build_lifespan(request_port: int):
    @asynccontextmanager
    async def lifespan(app):
        get_bootstrap_registry(app, request_port).start_all()

        yield

        stop_bootstrap_services()

    return lifespan
