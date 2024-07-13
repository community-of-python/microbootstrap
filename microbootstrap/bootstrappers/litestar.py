from __future__ import annotations
import typing

import litestar
import litestar.types
import sentry_sdk
from litestar import status_codes
from litestar.config.app import AppConfig
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig
from litestar.contrib.opentelemetry.middleware import OpenTelemetryInstrumentationMiddleware
from litestar.exceptions.http_exceptions import HTTPException

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.instruments import OpentelemetryInstrument, SentryInstrument
from microbootstrap.settings.litestar import LitestarBootstrapSettings


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
    def successful_bootstrap_result(self) -> dict[str, typing.Any]:
        return {"after_exception": [self.sentry_exception_catcher_hook]}


class LitetstarOpentelemetryInstrument(OpentelemetryInstrument):
    @property
    def successful_bootstrap_result(self) -> dict[str, typing.Any]:
        return {
            "middleware": OpenTelemetryInstrumentationMiddleware(
                OpenTelemetryConfig(
                    tracer_provider=self.tracer_provider,
                    exclude=self.instrument_config.opentelemetry_exclude_urls,
                ),
            ),
        }


class LitestarBootstrapper(
    ApplicationBootstrapper[LitestarBootstrapSettings, litestar.Litestar, AppConfig],
):
    sentry_instrument_type = LitestarSentryInstrument
    opentelemetry_instrument_type = LitetstarOpentelemetryInstrument
