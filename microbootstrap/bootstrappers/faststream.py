from __future__ import annotations
import typing

import faststream
import typing_extensions

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.settings import FastStreamOpentelemetryConfig, FastStreamSettings


class FastStreamBootstrapper(
    ApplicationBootstrapper[FastStreamSettings, faststream.FastStream, FastStreamConfig],
):
    application_config = FastStreamConfig()
    application_type = faststream.FastStream

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "title": self.settings.service_name,
            "version": self.settings.service_version,
            "description": self.settings.service_description,
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
        }


@FastStreamBootstrapper.use_instrument()
class FastStreamOpentelemetryInstrument(OpentelemetryInstrument):
    instrument_config: FastStreamOpentelemetryConfig

    def is_ready(self) -> bool:
        return bool(self.instrument_config.telemetry_middleware_cls and super().is_ready())

    def bootstrap_after(self, application: faststream.FastStream) -> dict[str, typing.Any]:  # type: ignore[override]
        if not (telemetry_middleware_cls := self.instrument_config.telemetry_middleware_cls) or not application.broker:
            return {}

        application.broker.add_middleware(telemetry_middleware_cls(tracer_provider=self.tracer_provider))
        return {}

    @classmethod
    def get_config_type(cls) -> type[FastStreamOpentelemetryConfig]:
        return FastStreamOpentelemetryConfig


FastStreamBootstrapper.use_instrument()(SentryInstrument)
FastStreamBootstrapper.use_instrument()(LoggingInstrument)
