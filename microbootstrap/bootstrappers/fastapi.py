import contextlib
import typing

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline_docs import enable_offline_docs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument, HealthCheckTypedDict
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
from microbootstrap.middlewares.fastapi import build_fastapi_logging_middleware
from microbootstrap.settings import FastApiSettings


ApplicationT = typing.TypeVar("ApplicationT", bound=fastapi.FastAPI)


class FastApiBootstrapper(
    ApplicationBootstrapper[FastApiSettings, fastapi.FastAPI, FastApiConfig],
):
    application_config = FastApiConfig()
    application_type = fastapi.FastAPI

    @contextlib.asynccontextmanager
    async def _lifespan_manager(self, _: fastapi.FastAPI) -> typing.AsyncIterator[None]:
        try:
            self.console_writer.print_bootstrap_table()
            yield
        finally:
            self.teardown()

    @contextlib.asynccontextmanager
    async def _wrapped_lifespan_manager(self, app: fastapi.FastAPI) -> typing.AsyncIterator[None]:
        assert self.application_config.lifespan  # noqa: S101
        async with self._lifespan_manager(app), self.application_config.lifespan(app):
            yield None

    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "debug": self.settings.service_debug,
            "lifespan": self._wrapped_lifespan_manager if self.application_config.lifespan else self._lifespan_manager,
        }


FastApiBootstrapper.use_instrument()(SentryInstrument)


@FastApiBootstrapper.use_instrument()
class FastApiSwaggerInstrument(SwaggerInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "title": self.instrument_config.service_name,
            "description": self.instrument_config.service_description,
            "docs_url": self.instrument_config.swagger_path,
            "version": self.instrument_config.service_version,
        }

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        if self.instrument_config.swagger_offline_docs:
            enable_offline_docs(application, static_files_handler=self.instrument_config.service_static_path)
        return application


@FastApiBootstrapper.use_instrument()
class FastApiCorsInstrument(CorsInstrument):
    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
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


FastApiBootstrapper.use_instrument()(PyroscopeInstrument)


@FastApiBootstrapper.use_instrument()
class FastApiOpentelemetryInstrument(OpentelemetryInstrument):
    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        FastAPIInstrumentor.instrument_app(
            application,
            tracer_provider=self.tracer_provider,
            excluded_urls=",".join(self.define_exclude_urls()),
        )
        return application


@FastApiBootstrapper.use_instrument()
class FastApiLoggingInstrument(LoggingInstrument):
    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        if not self.instrument_config.logging_turn_off_middleware:
            application.add_middleware(
                build_fastapi_logging_middleware(self.instrument_config.logging_exclude_endpoints),
            )
        return application


@FastApiBootstrapper.use_instrument()
class FastApiPrometheusInstrument(PrometheusInstrument[FastApiPrometheusConfig]):
    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
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
    def build_fastapi_health_check_router(self) -> fastapi.APIRouter:
        fastapi_router: typing.Final = fastapi.APIRouter(
            tags=["probes"],
            include_in_schema=self.instrument_config.health_checks_include_in_schema,
        )

        @fastapi_router.get(self.instrument_config.health_checks_path)
        async def health_check_handler() -> HealthCheckTypedDict:
            return self.render_health_check_data()

        return fastapi_router

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        application.include_router(self.build_fastapi_health_check_router())
        return application
