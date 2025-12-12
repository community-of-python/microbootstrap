from __future__ import annotations

from faststream.asgi import AsgiFastStream
from faststream.redis import RedisBroker

from microbootstrap.bootstrappers.faststream import FastStreamBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.granian_server import create_granian_server
from microbootstrap.settings import FastStreamSettings


class Settings(FastStreamSettings): ...


settings = Settings()


def create_app() -> AsgiFastStream:
    broker = RedisBroker()

    @broker.subscriber("first")
    @broker.publisher("second")
    def _(message: str) -> str:
        print(message)  # noqa: T201
        return "Hi from first handler!"

    @broker.subscriber("second")
    def _(message: str) -> None:
        print(message)  # noqa: T201

    app = FastStreamBootstrapper(settings).configure_application(FastStreamConfig(broker=broker)).bootstrap()

    @app.after_startup
    async def send_first_message() -> None:
        await broker.connect()
        await broker.publish("Hi from startup!", "first")

    return app


if __name__ == "__main__":
    create_granian_server("examples.faststream_app:create_app", settings, factory=True).serve()
