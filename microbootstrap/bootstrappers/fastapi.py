import contextlib
import http
import typing

import fastapi
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi_offline_docs import enable_offline_docs
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.fastapi import FastApiConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument, HealthCheckTypedDict
from microbootstrap.instruments.http_error_titles_instrument import HttpErrorTitlesInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.openapi_security_schemes import serialize_security_schemes
from microbootstrap.instruments.openapi_version_docs import SUPPORTED_HTTP_METHODS
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import FastApiPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
from microbootstrap.middlewares.fastapi import build_fastapi_logging_middleware
from microbootstrap.settings import FastApiSettings


_VALIDATION_DESCRIPTIONS: typing.Final = {
    "detail": "Validation errors describing the rejected request fields.",
    "loc": "Field names and array indices locating the invalid input.",
    "msg": "Human-readable validation error message.",
    "type": "Machine-readable validation error category.",
    "input": "Input value associated with the validation failure.",
    "ctx": "Additional context explaining the validation error.",
}


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
        if (
            self.instrument_config.openapi_version_docs is None
            and not self.instrument_config.security_schemes
            and not self.instrument_config.openapi_descriptions_enabled
        ):
            return application

        original_openapi: typing.Final = application.openapi

        def documented_openapi() -> dict[str, typing.Any]:
            openapi_schema: typing.Final = original_openapi()
            if self.instrument_config.openapi_descriptions_enabled:
                self._describe_generated_schemas(openapi_schema)
            if self.instrument_config.security_schemes:
                self._merge_security_schemes(openapi_schema)
            if self.instrument_config.openapi_version_docs is not None:
                self._document_operations(openapi_schema)
            return openapi_schema

        application.openapi = documented_openapi  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
        return application

    @staticmethod
    def _describe_generated_schemas(document: dict[str, typing.Any]) -> None:
        schemas = document.get("components", {}).get("schemas", {})
        for name in ("HTTPValidationError", "ValidationError"):
            if name not in schemas:
                continue
            definition = schemas[name]
            definition.setdefault("description", "Request validation failure reported by FastAPI.")
            for field_name, description in _VALIDATION_DESCRIPTIONS.items():
                if field_name in definition.get("properties", {}):
                    definition["properties"][field_name].setdefault("description", description)
        if "JsonValue" in schemas:
            schemas["JsonValue"].setdefault(
                "description", "JSON value: an object, array, string, number, boolean or null."
            )

    def _merge_security_schemes(self, openapi_schema: dict[str, typing.Any]) -> None:
        expected_schemes: typing.Final = serialize_security_schemes(self.instrument_config.security_schemes)
        components = openapi_schema.setdefault("components", {})
        security_schemes = components.setdefault("securitySchemes", {})
        self._validate_security_scheme_conflicts(security_schemes, expected_schemes)
        security_schemes.update(
            {name: scheme for name, scheme in expected_schemes.items() if name not in security_schemes}
        )

    def _document_operations(self, openapi_schema: dict[str, typing.Any]) -> None:
        for path, path_item in openapi_schema.get("paths", {}).items():
            if path.startswith("x-"):
                continue
            for method, operation in path_item.items():
                if method not in SUPPORTED_HTTP_METHODS:
                    continue
                documentation = self._build_version_documentation(
                    path,
                    method,
                    operation.get("description"),
                    operation.get("x-accept-versioning"),
                    has_existing_extension="x-accept-versioning" in operation,
                )
                if documentation is not None:
                    operation["x-accept-versioning"], operation["description"] = documentation


@FastApiBootstrapper.use_instrument()
class FastApiHttpErrorTitlesInstrument(HttpErrorTitlesInstrument):
    async def http_exception_response(self, request: fastapi.Request, exc: HTTPException) -> fastapi.Response:
        response = await fastapi.exception_handlers.http_exception_handler(request, exc)
        if exc.status_code >= http.HTTPStatus.BAD_REQUEST:
            return JSONResponse(
                {"detail": exc.detail, "title": self.title_for_status(exc.status_code)},
                status_code=exc.status_code,
                headers=exc.headers,
            )
        return response

    async def validation_error_response(self, _request: fastapi.Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": jsonable_encoder(exc.errors()),
                "title": self.title_for_status(http.HTTPStatus.UNPROCESSABLE_ENTITY),
            },
            status_code=http.HTTPStatus.UNPROCESSABLE_ENTITY,
        )

    async def internal_error_response(self, _request: fastapi.Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"detail": "Internal Server Error", "title": self.title_for_status(http.HTTPStatus.INTERNAL_SERVER_ERROR)},
            status_code=http.HTTPStatus.INTERNAL_SERVER_ERROR,
        )

    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "exception_handlers": {
                HTTPException: self.http_exception_response,
                RequestValidationError: self.validation_error_response,
                Exception: self.internal_error_response,
            }
        }

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        if application.exception_handlers.get(RequestValidationError) != self.validation_error_response:
            return application
        original_openapi: typing.Final = application.openapi

        def titled_openapi() -> dict[str, typing.Any]:
            document: typing.Final = original_openapi()
            schema = document.get("components", {}).get("schemas", {}).get("HTTPValidationError")
            if schema is not None:
                schema.setdefault("properties", {}).setdefault(
                    "title", {"type": "string", "description": "Short, human-readable summary of the HTTP error."}
                )
                required = schema.setdefault("required", [])
                if "title" not in required:
                    required.append("title")
            return document

        application.openapi = titled_openapi  # type: ignore[method-assign]  # FastAPI's public custom OpenAPI hook.
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
            excluded_urls=",".join(self.define_excluded_url_patterns()),
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
