from contextlib import asynccontextmanager

from .services import start_bootstrap_services, stop_bootstrap_services


def build_lifespan(request_port: int):
    @asynccontextmanager
    async def lifespan(app):
        start_bootstrap_services(app, request_port)

        yield

        stop_bootstrap_services()

    return lifespan
