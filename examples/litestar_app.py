from __future__ import annotations

import litestar

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.granian_server import create_granian_server


class Settings(LitestarSettings): ...


settings = Settings()


@litestar.get("/")
async def hello_world() -> dict[str, str]:
    return {"hello": "world"}


def create_app() -> litestar.Litestar:
    return (
        LitestarBootstrapper(settings).configure_application(LitestarConfig(route_handlers=[hello_world])).bootstrap()
    )


if __name__ == "__main__":
    create_granian_server("examples.litestar_app:create_app", settings, factory=True).serve()
