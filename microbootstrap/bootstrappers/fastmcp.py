from __future__ import annotations
import typing

import prometheus_client
import typing_extensions
from fastmcp import FastMCP
from starlette.responses import JSONResponse, Response

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastmcp import FastMcpConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument, HealthCheckTypedDict
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.prometheus_instrument import FastMcpPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.middlewares.fastmcp import FastMcpLoggingMiddleware
from microbootstrap.settings import FastMcpSettings


if typing.TYPE_CHECKING:
    from starlette.requests import Request


class KwargsFastMCP(FastMCP[typing.Any]):
    def __init__(self, **kwargs: typing.Any) -> None:  # noqa: ANN401
        super().__init__(**kwargs)


class FastMcpBootstrapper(
    ApplicationBootstrapper[FastMcpSettings, FastMCP[typing.Any], FastMcpConfig],
):
    application_config = FastMcpConfig()
    application_type = KwargsFastMCP

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "name": self.application_config.name or self.settings.service_name,
            "instructions": self.application_config.instructions or self.settings.service_description,
            "version": self.application_config.version or self.settings.service_version,
        }

    def bootstrap_before_instruments_after_app_created(
        self,
        application: FastMCP[typing.Any],
    ) -> FastMCP[typing.Any]:
        self.console_writer.print_bootstrap_table()
        return application


FastMcpBootstrapper.use_instrument()(SentryInstrument)
FastMcpBootstrapper.use_instrument()(PyroscopeInstrument)


@FastMcpBootstrapper.use_instrument()
class FastMcpLoggingInstrument(LoggingInstrument):
    def bootstrap_after(self, application: FastMCP[typing.Any]) -> FastMCP[typing.Any]:  # type: ignore[override]
        if not self.instrument_config.logging_turn_off_middleware:
            application.add_middleware(FastMcpLoggingMiddleware())
        return application


@FastMcpBootstrapper.use_instrument()
class FastMcpHealthChecksInstrument(HealthChecksInstrument):
    def bootstrap_after(self, application: FastMCP[typing.Any]) -> FastMCP[typing.Any]:  # type: ignore[override]
        @application.custom_route(
            self.instrument_config.health_checks_path,
            methods=["GET"],
            name="health_check",
            include_in_schema=self.instrument_config.health_checks_include_in_schema,
        )
        async def health_check_handler(request: Request) -> JSONResponse:  # noqa: ARG001
            response_data: HealthCheckTypedDict = self.render_health_check_data()
            return JSONResponse(response_data)

        return application


@FastMcpBootstrapper.use_instrument()
class FastMcpPrometheusInstrument(PrometheusInstrument[FastMcpPrometheusConfig]):
    def bootstrap_after(self, application: FastMCP[typing.Any]) -> FastMCP[typing.Any]:  # type: ignore[override]
        if not self.instrument_config.prometheus_register_route:
            return application

        @application.custom_route(
            self.instrument_config.prometheus_metrics_path,
            methods=["GET"],
            name="metrics",
            include_in_schema=self.instrument_config.prometheus_metrics_include_in_schema,
        )
        async def metrics_handler(request: Request) -> Response:  # noqa: ARG001
            registry: typing.Final = self.instrument_config.prometheus_registry or prometheus_client.REGISTRY
            return Response(
                prometheus_client.generate_latest(registry),
                headers={"content-type": prometheus_client.CONTENT_TYPE_LATEST},
            )

        return application

    @classmethod
    def get_config_type(cls) -> type[FastMcpPrometheusConfig]:
        return FastMcpPrometheusConfig
