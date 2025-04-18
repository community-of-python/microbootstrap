# example app using microbootstrap and litestar
import litestar

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.granian_server import create_granian_server


@litestar.get("/")
async def hello_world() -> dict[str, str]:
    return {"hello": "world"}


def create_app() -> litestar.Litestar:
    return (
        LitestarBootstrapper(LitestarSettings(pyroscope_endpoint="http://localhost:4040"))
        .configure_application(LitestarConfig(route_handlers=[hello_world]))
        .bootstrap()
    )


if __name__ == "__main__":
    create_granian_server("t:create_app", LitestarSettings(), factory=True).serve()
