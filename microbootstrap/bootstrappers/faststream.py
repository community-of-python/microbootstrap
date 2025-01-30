from __future__ import annotations
import typing

import typing_extensions
from faststream.asgi import AsgiFastStream

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.settings import FastStreamOpentelemetryConfig, FastStreamSettings


class FastStreamBootstrapper(
    ApplicationBootstrapper[FastStreamSettings, AsgiFastStream, FastStreamConfig],
):
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


# TODO: add health checks, prometheus
@FastStreamBootstrapper.use_instrument()
class FastStreamOpentelemetryInstrument(OpentelemetryInstrument):
    instrument_config: FastStreamOpentelemetryConfig

    def is_ready(self) -> bool:
        return bool(self.instrument_config.telemetry_middleware_cls and super().is_ready())

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if (telemetry_middleware_cls := self.instrument_config.telemetry_middleware_cls) and application.broker:
            application.broker.add_middleware(telemetry_middleware_cls(tracer_provider=self.tracer_provider))
        return application

    @classmethod
    def get_config_type(cls) -> type[FastStreamOpentelemetryConfig]:
        return FastStreamOpentelemetryConfig


FastStreamBootstrapper.use_instrument()(SentryInstrument)
FastStreamBootstrapper.use_instrument()(LoggingInstrument)
