import contextlib
import typing

import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline_docs import enable_offline_docs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator, metrics

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
        if not self._has_version_documentation() and not self.instrument_config.security_schemes:
            return application

        original_openapi: typing.Final = application.openapi

        def documented_openapi() -> dict[str, typing.Any]:
            openapi_schema: typing.Final = original_openapi()
            expected_schemes: typing.Final = self._prepare_security_scheme_updates(openapi_schema)
            version_documentation: typing.Final = self._prepare_version_documentation_updates(openapi_schema)
            if expected_schemes is not None:
                self._apply_security_scheme_updates(openapi_schema, expected_schemes)
            self._apply_version_documentation_updates(version_documentation)
            return openapi_schema

        application.openapi = documented_openapi  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
        return application

    def _prepare_security_scheme_updates(
        self,
        openapi_schema: dict[str, typing.Any],
    ) -> dict[str, dict[str, typing.Any]] | None:
        if not self.instrument_config.security_schemes:
            return None
        expected_schemes: typing.Final = self._expected_security_schemes()
        components = openapi_schema.get("components")
        if components is None:
            return expected_schemes
        if not isinstance(components, dict):
            message = "OpenAPI components must be a dictionary to configure security schemes."
            raise TypeError(message)
        security_schemes = components.get("securitySchemes")
        if security_schemes is None:
            return expected_schemes
        if not isinstance(security_schemes, dict):
            message = "OpenAPI components.securitySchemes must be a dictionary to configure security schemes."
            raise TypeError(message)
        self._validate_security_scheme_conflicts(security_schemes)
        return expected_schemes

    @staticmethod
    def _apply_security_scheme_updates(
        openapi_schema: dict[str, typing.Any],
        expected_schemes: dict[str, dict[str, typing.Any]],
    ) -> None:
        components = openapi_schema.get("components")
        if components is None:
            openapi_schema["components"] = {"securitySchemes": expected_schemes}
            return
        assert isinstance(components, dict)  # noqa: S101 - validated before application.
        security_schemes = components.get("securitySchemes")
        if security_schemes is None:
            components["securitySchemes"] = expected_schemes
            return
        assert isinstance(security_schemes, dict)  # noqa: S101 - validated before application.
        security_schemes.update(
            {name: scheme for name, scheme in expected_schemes.items() if name not in security_schemes}
        )

    def _prepare_version_documentation_updates(
        self,
        openapi_schema: dict[str, typing.Any],
    ) -> list[tuple[dict[str, typing.Any], dict[str, str | list[str]], str]]:
        updates: list[tuple[dict[str, typing.Any], dict[str, str | list[str]], str]] = []
        if not self._has_version_documentation():
            return updates
        paths = openapi_schema.get("paths")
        if not isinstance(paths, dict):
            return updates
        for path, path_item in paths.items():
            if not isinstance(path, str) or not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if not isinstance(method, str) or not isinstance(operation, dict):
                    continue
                documentation = self._prepare_version_documentation(
                    path,
                    method,
                    operation.get("description"),
                    operation.get("x-accept-versioning"),
                    has_existing_extension="x-accept-versioning" in operation,
                )
                if documentation is not None:
                    extension, description = documentation
                    updates.append((operation, extension, description))
        return updates

    @staticmethod
    def _apply_version_documentation_updates(
        updates: typing.Iterable[tuple[dict[str, typing.Any], dict[str, str | list[str]], str]],
    ) -> None:
        for operation, extension, description in updates:
            operation["x-accept-versioning"] = extension
            operation["description"] = description


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
        Instrumentator(**self.instrument_config.prometheus_instrumentator_params).add(
            metrics.default(
                custom_labels=self.instrument_config.prometheus_custom_labels,
            ),
        ).instrument(
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
