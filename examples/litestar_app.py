from __future__ import annotations
import logging

import litestar
import structlog

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.granian_server import create_granian_server
import random

class Settings(LitestarSettings): ...


settings = Settings( service_debug=False, sentry_additional_params={"debug":True})

@litestar.get("/")
async def hello_world() -> dict[str, str]:
    # 1/0
    structlog.get_logger().info("fdsjkfl")
    structlog.get_logger().error("testing structlog sentry integration", rand=random.gauss(0,1))
    return {"hello": "world"}
@litestar.get("/2")
async def hello_world2() -> dict[str, str]:
    # 1/0
    logging.getLogger().info("testing structlog sentry integration")
    logging.getLogger().critical("testing structlog sentry integration")
    return {"hello": "world"}

b: LitestarBootstrapper
def create_app() -> litestar.Litestar:
    global b
    b = LitestarBootstrapper(settings)
    t = b.configure_application(LitestarConfig(route_handlers=[hello_world, hello_world2])).bootstrap()
    # structlog.get_logger().error("testing structlog sentry integration")
    return t


if __name__ == "__main__":
    create_granian_server("examples.litestar_app:create_app", settings, factory=True).serve()
