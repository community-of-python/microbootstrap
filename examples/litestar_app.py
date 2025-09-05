from __future__ import annotations
import logging

import litestar
import structlog

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.granian_server import create_granian_server
from microbootstrap.instruments.logging_instrument import DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR, STRUCTLOG_PRE_CHAIN_PROCESSORS


class Settings(LitestarSettings): ...


settings = Settings(logging_buffer_capacity=2)
logger = logging.getLogger()

@litestar.get("/")
async def hello_world() -> dict[str, str]:
    # logger = logging.getLogger()
    # print(logger.handlers)
    # print(logging.getLogger().handlers)
    logger.info("Hi")
    return {"hello": "world"}


def create_app() -> litestar.Litestar:
    app= (
        LitestarBootstrapper(settings).configure_application(LitestarConfig(route_handlers=[hello_world])).bootstrap()
    )
    return app


if __name__ == "__main__":
    create_granian_server("examples.litestar_app:create_app", settings, factory=True).serve()
