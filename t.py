# example app using microbootstrap and litestar
import litestar

from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.settings import LitestarSettings


@litestar.get("/")
def hello_world() -> dict[str, str]:
    return {"hello": "world"}


def create_app() -> litestar.Litestar:
    return (
        LitestarBootstrapper(LitestarSettings())
        .configure_application(LitestarConfig(route_handlers=[hello_world]))
        .bootstrap()
    )


if __name__ == "__main__":
    from microbootstrap.granian_server import create_granian_server

    create_granian_server("t:create_app", LitestarSettings(), factory=True).serve()
