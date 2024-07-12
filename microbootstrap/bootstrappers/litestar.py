from __future__ import annotations
import typing

import litestar
import litestar.types
import sentry_sdk
from litestar import status_codes
from litestar.config.app import AppConfig
from litestar.exceptions.http_exceptions import HTTPException

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.instruments import SentryInstrument
from microbootstrap.settings.litestar import LitestarBootstrapSettings


class LitestarSentryInstrument(SentryInstrument):
    @staticmethod
    async def sentry_exception_catcher_hook(
        exception: Exception,
        _request_scope: litestar.types.Scope,
    ) -> None:
        if not isinstance(exception, HTTPException):
            sentry_sdk.capture_exception(exception)

        if exception.status_code >= status_codes.HTTP_500_INTERNAL_SERVER_ERROR:
            sentry_sdk.capture_exception(exception)

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready():
            # TODO: use some logger  # noqa: TD002
            print("Sentry is not ready for bootstrapping. Provide a sentry_dsn")  # noqa: T201
            return {}

        sentry_sdk.init(
            dsn=self.instrument_config.sentry_dsn,
            sample_rate=self.instrument_config.sentry_sample_rate,
            traces_sample_rate=self.instrument_config.sentry_traces_sample_rate,
            environment=self.instrument_config.sentry_environment,
            max_breadcrumbs=self.instrument_config.sentry_additional_paramsmax_breadcrumbs,
            attach_stacktrace=self.instrument_config.sentry_attach_stacktrace,
            integrations=self.instrument_config.sentry_integrations,
            **self.instrument_config.sentry_additional_params,
        )
        return {"after_exception": [self.sentry_exception_catcher_hook]}


class LitestarBootstrapper(
    ApplicationBootstrapper[LitestarBootstrapSettings, litestar.Litestar, AppConfig],
):
    sentry_instrument_type = LitestarSentryInstrument
