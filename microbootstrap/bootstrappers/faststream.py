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
from microbootstrap.instruments.opentelemetry_instrument import BaseOpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import BasePrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.settings import FastStreamOpentelemetryConfig, FastStreamSettings


class FastStreamBootstrapper(ApplicationBootstrapper[FastStreamSettings, AsgiFastStream, FastStreamConfig]):
    application_config = FastStreamConfig()
    application_type = AsgiFastStream

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


@FastStreamBootstrapper.use_instrument()
class FastStreamOpentelemetryInstrument(BaseOpentelemetryInstrument[FastStreamOpentelemetryConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.telemetry_middleware_cls and super().is_ready())

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if (telemetry_middleware_cls := self.instrument_config.telemetry_middleware_cls) and application.broker:
            application.broker.add_middleware(telemetry_middleware_cls(tracer_provider=self.tracer_provider))
        return application

    @classmethod
    def get_config_type(cls) -> type[FastStreamOpentelemetryConfig]:
        return FastStreamOpentelemetryConfig


@FastStreamBootstrapper.use_instrument()
class FastStreamLoggingInstrument(LoggingInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"logger": structlog.get_logger("faststream")}


@FastStreamBootstrapper.use_instrument()
class FastStreamPrometheusInstrument(PrometheusInstrument[BasePrometheusConfig]):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"asgi_routes": ("/metrics", prometheus_client.make_asgi_app(prometheus_client.CollectorRegistry()))}


@FastStreamBootstrapper.use_instrument()
class FastStreamHealthChecksInstrument(HealthChecksInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        @handle_get
        async def check_health(scope: typing.Any) -> AsgiResponse:  # noqa: ANN401, ARG001
            health_check_data = await self.health_check.check_health()
            return (
                AsgiResponse(json.dumps(health_check_data).encode(), 200, headers={"content-type": "text/plain"})
                if health_check_data["health_status"]
                else AsgiResponse(b"Service is unhealthy", 500, headers={"content-type": "application/json"})
            )

        return {"asgi_routes": ("/health", check_health)}
