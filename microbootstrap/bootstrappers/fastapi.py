import typing

import fastapi
import typing_extensions
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline_docs import enable_offline_docs
from health_checks.fastapi_healthcheck import build_fastapi_health_check_router
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator
from sentry_sdk.integrations.fastapi import FastApiIntegration

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
from microbootstrap.middlewares.fastapi import build_fastapi_logging_middleware
from microbootstrap.settings import FastApiSettings


class FastApiBootstrapper(
    ApplicationBootstrapper[FastApiSettings, fastapi.FastAPI, FastApiConfig],
):
    application_config = FastApiConfig()
    application_type = fastapi.FastAPI

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "debug": self.settings.service_debug,
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
        }


@FastApiBootstrapper.use_instrument()
class FastApiSentryInstrument(SentryInstrument):
    def bootstrap(self) -> None:
        for sentry_integration in self.instrument_config.sentry_integrations:
            if isinstance(sentry_integration, FastApiIntegration):
                break
        else:
            self.instrument_config.sentry_integrations.append(FastApiIntegration())
        super().bootstrap()


@FastApiBootstrapper.use_instrument()
class FastApiSwaggerInstrument(SwaggerInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "title": self.instrument_config.service_name,
            "description": self.instrument_config.service_description,
            "docs_url": self.instrument_config.swagger_path,
            "version": self.instrument_config.service_version,
        }

    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        if self.instrument_config.swagger_offline_docs:
            enable_offline_docs(application, static_files_handler=self.instrument_config.service_static_path)
        return application


@FastApiBootstrapper.use_instrument()
class FastApiCorsInstrument(CorsInstrument):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=self.instrument_config.cors_allowed_origins,
            allow_methods=self.instrument_config.cors_allowed_methods,
            allow_headers=self.instrument_config.cors_allowed_headers,
            allow_credentials=self.instrument_config.cors_allowed_credentials,
            allow_origin_regex=self.instrument_config.cors_allowed_origin_regex,
            expose_headers=self.instrument_config.cors_exposed_headers,
            max_age=self.instrument_config.cors_max_age,
        )
        return application


@FastApiBootstrapper.use_instrument()
class FastApiOpentelemetryInstrument(OpentelemetryInstrument):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        FastAPIInstrumentor.instrument_app(
            application,
            tracer_provider=self.tracer_provider,
            excluded_urls=self.instrument_config.opentelemetry_exclude_urls,
        )
        return application


@FastApiBootstrapper.use_instrument()
class FastApiLoggingInstrument(LoggingInstrument):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        application.add_middleware(
            build_fastapi_logging_middleware(self.instrument_config.logging_exclude_endpoints),
        )
        return application


@FastApiBootstrapper.use_instrument()
class FastApiPrometheusInstrument(PrometheusInstrument[FastApiPrometheusConfig]):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        Instrumentator(**self.instrument_config.prometheus_instrumentator_params).instrument(
            application,
            **self.instrument_config.prometheus_instrument_params,
        ).expose(
            application,
            endpoint=self.instrument_config.prometheus_metrics_path,
            include_in_schema=self.instrument_config.prometheus_metrics_include_in_schema,
            **self.instrument_config.prometheus_expose_params,
        )
        return application

    @classmethod
    def get_config_type(cls) -> type[FastApiPrometheusConfig]:
        return FastApiPrometheusConfig


@FastApiBootstrapper.use_instrument()
class FastApiHealthChecksInstrument(HealthChecksInstrument):
    def bootstrap_after(self, application: fastapi.FastAPI) -> fastapi.FastAPI:
        application.include_router(
            build_fastapi_health_check_router(
                health_check=self.health_check,
                health_check_endpoint=self.instrument_config.health_checks_path,
                include_in_schema=self.instrument_config.health_checks_include_in_schema,
            ),
        )
        return application
