from __future__ import annotations
import typing

import litestar
import litestar.types
import sentry_sdk
import typing_extensions
from litestar import status_codes
from litestar.config.app import AppConfig
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.contrib.opentelemetry.middleware import OpenTelemetryInstrumentationMiddleware
from litestar.contrib.prometheus import PrometheusConfig as LitestarPrometheusConfig
from litestar.contrib.prometheus import PrometheusController
from litestar.exceptions.http_exceptions import HTTPException

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemery_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import PrometheusInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.middlewares.litestar import build_litestar_logging_middleware
from microbootstrap.settings import BootstrapSettings


class LitestarBootstrapper(
    ApplicationBootstrapper[BootstrapSettings, litestar.Litestar, AppConfig],
):
    application_config = AppConfig()
    application_type = litestar.Litestar

    def extra_bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {"on_shutdown": [self.teardown]}


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

    @property
    def bootsrap_final_result(self) -> dict[str, typing.Any]:
        return {"after_exception": [self.sentry_exception_catcher_hook]}


@LitestarBootstrapper.use_instrument()
class LitetstarOpentelemetryInstrument(OpentelemetryInstrument):
    @property
    def bootsrap_final_result(self) -> dict[str, typing.Any]:
        return {
            "middleware": OpenTelemetryInstrumentationMiddleware(
                LitestarOpentelemetryConfig(
                    tracer_provider=self.tracer_provider,
                    exclude=self.instrument_config.opentelemetry_exclude_urls,
                ),
            ),
        }


@LitestarBootstrapper.use_instrument()
class LitestarLoggingInstrument(LoggingInstrument):
    @property
    def bootsrap_final_result(self) -> dict[str, typing.Any]:
        return {"middleware": build_litestar_logging_middleware(self.instrument_config.logging_exclude_endpoings)}


@LitestarBootstrapper.use_instrument()
class LitestarPrometheusInstrument(PrometheusInstrument):
    @property
    def bootsrap_final_result(self) -> dict[str, typing.Any]:
        class LitestarPrometheusController(PrometheusController):
            path = self.instrument_config.prometheus_metrics_path
            openmetrics_format = True

        litestar_prometheus_config: typing.Final = LitestarPrometheusConfig(
            app_name=self.instrument_config.service_name,
            **self.instrument_config.prometheus_additional_params,
        )

        return {"route_handlers": [LitestarPrometheusController], "middleware": [litestar_prometheus_config.middleware]}
