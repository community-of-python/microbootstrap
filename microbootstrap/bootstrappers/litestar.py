from __future__ import annotations
import typing

import litestar
import litestar.types
import sentry_sdk
import typing_extensions
from litestar import status_codes
from litestar.config.app import AppConfig as LitestarConfig
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.contrib.prometheus import PrometheusConfig as LitestarPrometheusConfig
from litestar.contrib.prometheus import PrometheusController
from litestar.exceptions.http_exceptions import HTTPException

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import PrometheusInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.middlewares.litestar import build_litestar_logging_middleware
from microbootstrap.settings import LitestarSettings


class LitestarBootstrapper(
    ApplicationBootstrapper[LitestarSettings, litestar.Litestar, LitestarConfig],
):
    application_config = LitestarConfig()
    application_type = litestar.Litestar

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "debug": self.settings.service_debug,
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
        }


@LitestarBootstrapper.use_instrument()
class LitestarSentryInstrument(SentryInstrument):
    @staticmethod
    async def sentry_exception_catcher_hook(
        exception: Exception,
        _request_scope: litestar.types.Scope,
    ) -> None:
        if (
            not isinstance(exception, HTTPException)
            or exception.status_code >= status_codes.HTTP_500_INTERNAL_SERVER_ERROR
        ):
            sentry_sdk.capture_exception(exception)

    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"after_exception": [self.sentry_exception_catcher_hook]}


@LitestarBootstrapper.use_instrument()
class LitetstarOpentelemetryInstrument(OpentelemetryInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "middleware": [
                LitestarOpentelemetryConfig(
                    tracer_provider=self.tracer_provider,
                    exclude=self.instrument_config.opentelemetry_exclude_urls,
                ).middleware,
            ],
        }


@LitestarBootstrapper.use_instrument()
class LitestarLoggingInstrument(LoggingInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"middleware": [build_litestar_logging_middleware(self.instrument_config.logging_exclude_endpoints)]}


@LitestarBootstrapper.use_instrument()
class LitestarPrometheusInstrument(PrometheusInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        class LitestarPrometheusController(PrometheusController):
            path = self.instrument_config.prometheus_metrics_path
            openmetrics_format = True

        litestar_prometheus_config: typing.Final = LitestarPrometheusConfig(
            app_name=self.instrument_config.service_name,
            **self.instrument_config.prometheus_additional_params,
        )

        return {"route_handlers": [LitestarPrometheusController], "middleware": [litestar_prometheus_config.middleware]}
