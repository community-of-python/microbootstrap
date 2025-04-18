from __future__ import annotations
import json
import typing

import prometheus_client
import structlog
import typing_extensions
from faststream.asgi import AsgiFastStream, AsgiResponse
from faststream.asgi import get as handle_get

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import (
    BaseOpentelemetryInstrument,
    FastStreamOpentelemetryConfig,
)
from microbootstrap.instruments.prometheus_instrument import FastStreamPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.settings import FastStreamSettings


class KwargsAsgiFastStream(AsgiFastStream):
    def __init__(self, **kwargs: typing.Any) -> None:  # noqa: ANN401
        # `broker` argument is positional-only
        super().__init__(kwargs.pop("broker", None), **kwargs)


class FastStreamBootstrapper(ApplicationBootstrapper[FastStreamSettings, AsgiFastStream, FastStreamConfig]):
    application_config = FastStreamConfig()
    application_type = KwargsAsgiFastStream

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "title": self.settings.service_name,
            "version": self.settings.service_version,
            "description": self.settings.service_description,
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
            "asyncapi_path": self.settings.asyncapi_path,
        }


FastStreamBootstrapper.use_instrument()(SentryInstrument)
FastStreamBootstrapper.use_instrument()(PyroscopeInstrument)


@FastStreamBootstrapper.use_instrument()
class FastStreamOpentelemetryInstrument(BaseOpentelemetryInstrument[FastStreamOpentelemetryConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.opentelemetry_middleware_cls and super().is_ready())

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if self.instrument_config.opentelemetry_middleware_cls and application.broker:
            application.broker.add_middleware(
                self.instrument_config.opentelemetry_middleware_cls(tracer_provider=self.tracer_provider)
            )
        return application

    @classmethod
    def get_config_type(cls) -> type[FastStreamOpentelemetryConfig]:
        return FastStreamOpentelemetryConfig


@FastStreamBootstrapper.use_instrument()
class FastStreamLoggingInstrument(LoggingInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"logger": structlog.get_logger("microbootstrap-faststream")}


@FastStreamBootstrapper.use_instrument()
class FastStreamPrometheusInstrument(PrometheusInstrument[FastStreamPrometheusConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_middleware_cls and super().is_ready())

    def bootstrap_before(self) -> dict[str, typing.Any]:
        self.collector_registry = prometheus_client.CollectorRegistry()
        return {
            "asgi_routes": (
                (
                    self.instrument_config.prometheus_metrics_path,
                    prometheus_client.make_asgi_app(self.collector_registry),
                ),
            )
        }

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if self.instrument_config.prometheus_middleware_cls and application.broker:
            application.broker.add_middleware(
                self.instrument_config.prometheus_middleware_cls(registry=self.collector_registry)
            )
        return application

    @classmethod
    def get_config_type(cls) -> type[FastStreamPrometheusConfig]:
        return FastStreamPrometheusConfig


@FastStreamBootstrapper.use_instrument()
class FastStreamHealthChecksInstrument(HealthChecksInstrument):
    def bootstrap(self) -> None: ...
    def bootstrap_before(self) -> dict[str, typing.Any]:
        @handle_get
        async def check_health(scope: typing.Any) -> AsgiResponse:  # noqa: ANN401, ARG001
            return (
                AsgiResponse(
                    json.dumps(self.render_health_check_data()).encode(), 200, headers={"content-type": "text/plain"}
                )
                if await self.define_health_status()
                else AsgiResponse(b"Service is unhealthy", 500, headers={"content-type": "application/json"})
            )

        return {"asgi_routes": ((self.instrument_config.health_checks_path, check_health),)}

    async def define_health_status(self) -> bool:
        return await self.application.broker.ping(timeout=5) if self.application and self.application.broker else False

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        self.application = application
        return application
