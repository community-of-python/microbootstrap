from __future__ import annotations
import re
import typing

import prometheus_client
import typing_extensions
from fastmcp import FastMCP
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.util.http import ExcludeList, get_excluded_urls
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator import metrics as instrumentator_metrics
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Match, Mount, Route

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastmcp import FastMcpConfig
from microbootstrap.instruments import opentelemetry_instrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument, HealthCheckTypedDict
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.prometheus_instrument import FastMcpPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.middlewares.fastmcp import FastMcpLoggingMiddleware, FastMcpPrometheusMiddleware
from microbootstrap.settings import FastMcpSettings


if typing.TYPE_CHECKING:
    from fastmcp.server.http import StarletteWithLifespan
    from starlette.requests import Request
    from starlette.types import Scope


StarletteT = typing.TypeVar("StarletteT", bound=Starlette)


class KwargsFastMCP(FastMCP[typing.Any]):
    def __init__(self, **kwargs: typing.Any) -> None:  # noqa: ANN401
        super().__init__(**kwargs)
        self.http_application_postprocessors: list[typing.Callable[[StarletteWithLifespan], StarletteWithLifespan]] = []

    def add_http_application_postprocessor(
        self, postprocessor: typing.Callable[[StarletteWithLifespan], StarletteWithLifespan]
    ) -> None:
        self.http_application_postprocessors.append(postprocessor)

    def http_app(self, *args: typing.Any, **kwargs: typing.Any) -> StarletteWithLifespan:  # noqa: ANN401
        # ASGI application is created by the user after bootstrap, so instruments subscribe to its creation
        http_application = super().http_app(*args, **kwargs)
        for postprocessor in self.http_application_postprocessors:
            http_application = postprocessor(http_application)
        return http_application


def build_fastmcp_route_details_from_scope(
    scope: Scope,
    routes: typing.Iterable[typing.Any],
) -> tuple[str, dict[str, str]]:
    method: typing.Final = str(scope.get("method", "HTTP")).strip()
    for route in routes:
        if isinstance(route, (Route, Mount)) and route.matches(scope)[0] == Match.FULL:
            return opentelemetry_instrument.build_span_name(method, route.path), {"http.route": route.path}
    # Unmatched paths get no `http.route` to keep its cardinality low
    return method, {}


class FastMcpBootstrapper(
    ApplicationBootstrapper[FastMcpSettings, KwargsFastMCP, FastMcpConfig],
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
        application: KwargsFastMCP,
    ) -> KwargsFastMCP:
        self.console_writer.print_bootstrap_table()
        return application


FastMcpBootstrapper.use_instrument()(SentryInstrument)
FastMcpBootstrapper.use_instrument()(PyroscopeInstrument)


@FastMcpBootstrapper.use_instrument()
class FastMcpOpentelemetryInstrument(
    opentelemetry_instrument.BaseOpentelemetryInstrument[opentelemetry_instrument.OpentelemetryConfig]
):
    def bootstrap_after(self, application: FastMCP[typing.Any]) -> FastMCP[typing.Any]:  # type: ignore[override]
        if isinstance(application, KwargsFastMCP):
            application.add_http_application_postprocessor(self.__instrument_http_app)
        return application

    def __instrument_http_app(self, http_application: StarletteT) -> StarletteT:
        # `StarletteInstrumentor` marks applications the same way, so each application is instrumented once
        if getattr(http_application, "_is_instrumented_by_opentelemetry", False):
            return http_application

        def build_route_details(scope: Scope) -> tuple[str, dict[str, str]]:
            return build_fastmcp_route_details_from_scope(scope, http_application.routes)

        http_application.add_middleware(
            OpenTelemetryMiddleware,
            tracer_provider=self.tracer_provider,
            default_span_details=build_route_details,
            excluded_urls=opentelemetry_instrument.CombinedExcludeList(
                ExcludeList(self.define_exclude_urls()),
                get_excluded_urls("STARLETTE"),
            ),
        )
        http_application._is_instrumented_by_opentelemetry = True  # type: ignore[attr-defined]  # noqa: SLF001
        return http_application

    @classmethod
    def get_config_type(cls) -> type[opentelemetry_instrument.OpentelemetryConfig]:
        return opentelemetry_instrument.OpentelemetryConfig


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
        if isinstance(application, KwargsFastMCP):
            application.add_http_application_postprocessor(self.__instrument_http_app)
        if self.instrument_config.prometheus_tool_metrics:
            application.add_middleware(
                FastMcpPrometheusMiddleware(
                    registry=self.instrument_config.prometheus_registry,
                    custom_labels=self.instrument_config.prometheus_custom_labels,
                )
            )

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

    def __instrument_http_app(self, http_application: StarletteT) -> StarletteT:
        # Same instrumentator as in the FastAPI bootstrapper: requests are counted by route template
        # (`handler="/mcp"`, `handler="/health/"`), unknown paths are grouped into `handler="none"`.
        registry: typing.Final = self.instrument_config.prometheus_registry or prometheus_client.REGISTRY
        instrumentator_params: typing.Final = {
            "excluded_handlers": [f"^{re.escape(self.instrument_config.prometheus_metrics_path)}$"],
            "registry": registry,
            **self.instrument_config.prometheus_instrumentator_params,
        }
        Instrumentator(**instrumentator_params).add(
            instrumentator_metrics.default(
                registry=registry,
                custom_labels=self.instrument_config.prometheus_custom_labels,
            ),
        ).instrument(http_application, **self.instrument_config.prometheus_instrument_params)
        return http_application

    @classmethod
    def get_config_type(cls) -> type[FastMcpPrometheusConfig]:
        return FastMcpPrometheusConfig
