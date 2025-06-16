from __future__ import annotations
import typing

from microbootstrap.bootstrappers.fastapi import FastApiBootstrapper
from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import FastApiSettings


if typing.TYPE_CHECKING:
    import fastapi


class Settings(FastApiSettings): ...


settings = Settings()


def create_app() -> fastapi.FastAPI:
    app = FastApiBootstrapper(settings).bootstrap()

    @app.get("/")
    async def hello_world() -> dict[str, str]:
        return {"hello": "world"}

    return app


if __name__ == "__main__":
    create_granian_server("examples.fastapi_app:create_app", settings, factory=True).serve()
