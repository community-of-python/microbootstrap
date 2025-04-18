from __future__ import annotations
import typing

import litestar
import litestar.exceptions
import litestar.types
import typing_extensions
from litestar import openapi
from litestar.config.cors import CORSConfig as LitestarCorsConfig
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.contrib.prometheus import PrometheusConfig, PrometheusController
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar_offline_docs import generate_static_files_config
from sentry_sdk.integrations.litestar import LitestarIntegration

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument, HealthCheckTypedDict
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import LitestarPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
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
    def bootstrap(self) -> None:
        for sentry_integration in self.instrument_config.sentry_integrations:
            if isinstance(sentry_integration, LitestarIntegration):
                break
        else:
            self.instrument_config.sentry_integrations.append(LitestarIntegration())
        super().bootstrap()


@LitestarBootstrapper.use_instrument()
class LitestarSwaggerInstrument(SwaggerInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        render_plugins: typing.Final = (
            (
                SwaggerRenderPlugin(
                    js_url=f"{self.instrument_config.service_static_path}/swagger-ui-bundle.js",
                    css_url=f"{self.instrument_config.service_static_path}/swagger-ui.css",
                    standalone_preset_js_url=(
                        f"{self.instrument_config.service_static_path}/swagger-ui-standalone-preset.js"
                    ),
                ),
            )
            if self.instrument_config.swagger_offline_docs
            else (SwaggerRenderPlugin(),)
        )

        all_swagger_params: typing.Final = {
            "path": self.instrument_config.swagger_path,
            "title": self.instrument_config.service_name,
            "version": self.instrument_config.service_version,
            "description": self.instrument_config.service_description,
            "render_plugins": render_plugins,
        } | self.instrument_config.swagger_extra_params

        bootstrap_result: typing.Final[dict[str, typing.Any]] = {
            "openapi_config": openapi.OpenAPIConfig(**all_swagger_params),
        }
        if self.instrument_config.swagger_offline_docs:
            bootstrap_result["static_files_config"] = [
                generate_static_files_config(static_files_handler_path=self.instrument_config.service_static_path),
            ]
        return bootstrap_result


@LitestarBootstrapper.use_instrument()
class LitestarCorsInstrument(CorsInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "cors_config": LitestarCorsConfig(
                allow_origins=self.instrument_config.cors_allowed_origins,
                allow_methods=self.instrument_config.cors_allowed_methods,  # type: ignore[arg-type]
                allow_headers=self.instrument_config.cors_allowed_headers,
                allow_credentials=self.instrument_config.cors_allowed_credentials,
                allow_origin_regex=self.instrument_config.cors_allowed_origin_regex,
                expose_headers=self.instrument_config.cors_exposed_headers,
                max_age=self.instrument_config.cors_max_age,
            ),
        }


LitestarBootstrapper.use_instrument()(PyroscopeInstrument)


@LitestarBootstrapper.use_instrument()
class LitestarOpentelemetryInstrument(OpentelemetryInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "middleware": [
                LitestarOpentelemetryConfig(
                    tracer_provider=self.tracer_provider,
                    exclude=self.define_exclude_urls(),
                ).middleware,
            ],
        }


@LitestarBootstrapper.use_instrument()
class LitestarLoggingInstrument(LoggingInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        if self.instrument_config.logging_turn_off_middleware:
            return {}

        return {"middleware": [build_litestar_logging_middleware(self.instrument_config.logging_exclude_endpoints)]}


@LitestarBootstrapper.use_instrument()
class LitestarPrometheusInstrument(PrometheusInstrument[LitestarPrometheusConfig]):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        class LitestarPrometheusController(PrometheusController):
            path = self.instrument_config.prometheus_metrics_path
            include_in_schema = self.instrument_config.prometheus_metrics_include_in_schema
            openmetrics_format = True

        litestar_prometheus_config: typing.Final = PrometheusConfig(
            app_name=self.instrument_config.service_name,
            **self.instrument_config.prometheus_additional_params,
        )

        return {"route_handlers": [LitestarPrometheusController], "middleware": [litestar_prometheus_config.middleware]}

    @classmethod
    def get_config_type(cls) -> type[LitestarPrometheusConfig]:
        return LitestarPrometheusConfig


@LitestarBootstrapper.use_instrument()
class LitestarHealthChecksInstrument(HealthChecksInstrument):
    def build_litestar_health_check_router(self) -> litestar.Router:
        @litestar.get(media_type=litestar.MediaType.JSON)
        async def health_check_handler() -> HealthCheckTypedDict:
            return self.render_health_check_data()

        return litestar.Router(
            path=self.instrument_config.health_checks_path,
            route_handlers=[health_check_handler],
            tags=["probes"],
            include_in_schema=self.instrument_config.health_checks_include_in_schema,
        )

    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"route_handlers": [self.build_litestar_health_check_router()]}
