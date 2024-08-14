from __future__ import annotations
import typing

import litestar
import litestar.types
import typing_extensions
from litestar import openapi
from litestar.config.app import AppConfig as LitestarConfig
from litestar.config.cors import CORSConfig as LitestarCorsConfig
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig as LitestarOpentelemetryConfig
from litestar.contrib.prometheus import PrometheusConfig as LitestarPrometheusConfig
from litestar.contrib.prometheus import PrometheusController
from litestar_offline_docs import generate_static_files_config
from sentry_sdk.integrations.litestar import LitestarIntegration

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import PrometheusInstrument
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
        class LitestarOpenAPIController(openapi.OpenAPIController):
            path = self.instrument_config.swagger_path
            if self.instrument_config.swagger_offline_docs:
                swagger_ui_standalone_preset_js_url = (
                    f"{self.instrument_config.service_static_path}/swagger-ui-standalone-preset.js"
                )
                swagger_bundle_path: str = f"{self.instrument_config.service_static_path}/swagger-ui-bundle.js"
                swagger_css_url: str = f"{self.instrument_config.service_static_path}/swagger-ui.css"

        openapi_config: typing.Final = openapi.OpenAPIConfig(
            title=self.instrument_config.service_name,
            version=self.instrument_config.service_version,
            description=self.instrument_config.service_description,
            openapi_controller=LitestarOpenAPIController,
            **self.instrument_config.swagger_extra_params,
        )

        bootstrap_result = {}
        if self.instrument_config.swagger_offline_docs:
            bootstrap_result["static_files_config"] = [
                generate_static_files_config(static_files_handler_path=self.instrument_config.service_static_path),
            ]
        return {
            **bootstrap_result,
            "openapi_config": openapi_config,
        }


@LitestarBootstrapper.use_instrument()
class LitestarCorsInstrument(CorsInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "cors_config": LitestarCorsConfig(
                allow_origins=self.instrument_config.cors_allowed_origins,
                allow_methods=self.instrument_config.cors_allowed_methods,
                allow_headers=self.instrument_config.cors_allowed_headers,
                allow_credentials=self.instrument_config.cors_allowed_credentials,
                allow_origin_regex=self.instrument_config.cors_allowed_origin_regex,
                expose_headers=self.instrument_config.cors_exposed_headers,
                max_age=self.instrument_config.cors_max_age,
            ),
        }


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
