from __future__ import annotations
import dataclasses
import typing

import litestar
import typing_extensions
from litestar import openapi
from litestar.config.cors import CORSConfig as LitestarCorsConfig
from litestar.contrib.opentelemetry.config import (
    OpenTelemetryConfig as LitestarOpentelemetryConfig,
)
from litestar.contrib.prometheus import PrometheusConfig, PrometheusController
from litestar.middleware import ASGIMiddleware
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.types.asgi_types import ASGIApp, Scope
from litestar_offline_docs import generate_static_files_config
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.util.http import get_excluded_urls
from sentry_sdk.integrations.litestar import LitestarIntegration

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.cors_instrument import CorsInstrument
from microbootstrap.instruments.health_checks_instrument import (
    HealthChecksInstrument,
    HealthCheckTypedDict,
)
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.openapi_security_schemes import (
    OpenApiApiKeySecurityScheme,
    OpenApiHttpSecurityScheme,
    OpenApiOAuth2SecurityScheme,
    OpenApiOAuthFlow,
    OpenApiOAuthFlows,
    OpenApiOpenIdConnectSecurityScheme,
    _OpenApiSecurityScheme,
    serialize_security_schemes,
)
from microbootstrap.instruments.openapi_version_docs import SUPPORTED_HTTP_METHODS
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import (
    LitestarPrometheusConfig,
    PrometheusInstrument,
)
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.instruments.swagger_instrument import SwaggerInstrument
from microbootstrap.middlewares.litestar import build_litestar_logging_middleware
from microbootstrap.settings import LitestarSettings


ApplicationT = typing.TypeVar("ApplicationT", bound=litestar.Litestar)


@dataclasses.dataclass
class AcceptVersionedOperation(openapi.spec.Operation):
    accept_versioning: dict[str, str | list[str]] | None = dataclasses.field(
        default=None,
        metadata={"alias": "x-accept-versioning"},
    )


if typing.TYPE_CHECKING:
    from litestar.contrib.opentelemetry import OpenTelemetryConfig
    from litestar.types import ASGIApp, Scope
    from litestar.types.asgi_types import Receive, Send


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

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        if (self.instrument_config.openapi_version_docs is None and not self.instrument_config.security_schemes) or (
            application.openapi_schema is None
        ):
            return application
        if self.instrument_config.security_schemes:
            self._merge_security_schemes(application.openapi_schema)
        if self.instrument_config.openapi_version_docs is not None:
            self._document_operations(application.openapi_schema)
        return application

    def _merge_security_schemes(self, openapi_schema: openapi.spec.OpenAPI) -> None:
        expected_schemes: typing.Final = serialize_security_schemes(self.instrument_config.security_schemes)
        security_schemes = openapi_schema.components.security_schemes
        if security_schemes is not None:
            canonical_schemes: typing.Final = {
                name: scheme.to_schema() if isinstance(scheme, openapi.spec.SecurityScheme) else scheme
                for name, scheme in security_schemes.items()
            }
            self._validate_security_scheme_conflicts(canonical_schemes, expected_schemes)
        configured_schemes = {
            scheme_name: self._build_litestar_security_scheme(security_scheme)
            for scheme_name, security_scheme in self.instrument_config.security_schemes.items()
        }
        if security_schemes is None:
            openapi_schema.components.security_schemes = typing.cast(
                "dict[str, openapi.spec.SecurityScheme | openapi.spec.Reference]",
                configured_schemes,
            )
            return
        security_schemes.update(
            {name: scheme for name, scheme in configured_schemes.items() if name not in security_schemes}
        )

    def _document_operations(self, openapi_schema: openapi.spec.OpenAPI) -> None:
        if openapi_schema.paths is None:
            return
        for path, path_item in openapi_schema.paths.items():
            for method in SUPPORTED_HTTP_METHODS:
                operation = getattr(path_item, method)
                if operation is None:
                    continue
                existing_extension = (
                    operation.accept_versioning if isinstance(operation, AcceptVersionedOperation) else None
                )
                documentation = self._build_version_documentation(
                    path,
                    method,
                    operation.description,
                    existing_extension,
                    has_existing_extension=existing_extension is not None,
                )
                if documentation is None:
                    continue
                extension, description = documentation
                if type(operation) is openapi.spec.Operation:
                    init_fields = {
                        field.name: getattr(operation, field.name)
                        for field in dataclasses.fields(openapi.spec.Operation)
                        if field.init
                    }
                    operation = AcceptVersionedOperation(**init_fields, accept_versioning=extension)
                    setattr(path_item, method, operation)
                elif type(operation) is not AcceptVersionedOperation:
                    message = (
                        f"OpenAPI operation {type(operation).__name__} is not supported "
                        "for Accept version documentation."
                    )
                    raise TypeError(message)
                operation.accept_versioning = extension
                operation.description = description

    @classmethod
    def _build_litestar_security_scheme(cls, security_scheme: _OpenApiSecurityScheme) -> openapi.spec.SecurityScheme:
        if isinstance(security_scheme, OpenApiHttpSecurityScheme):
            return openapi.spec.SecurityScheme(
                type=security_scheme.type,
                scheme=security_scheme.scheme,
                bearer_format=security_scheme.bearer_format,
                description=security_scheme.description,
            )
        if isinstance(security_scheme, OpenApiApiKeySecurityScheme):
            return openapi.spec.SecurityScheme(
                type=security_scheme.type,
                name=security_scheme.name,
                security_scheme_in=security_scheme.location,
                description=security_scheme.description,
            )
        if isinstance(security_scheme, OpenApiOAuth2SecurityScheme):
            return openapi.spec.SecurityScheme(
                type=security_scheme.type,
                flows=cls._build_litestar_oauth_flows(security_scheme.flows),
                description=security_scheme.description,
            )
        if isinstance(security_scheme, OpenApiOpenIdConnectSecurityScheme):
            return openapi.spec.SecurityScheme(
                type=security_scheme.type,
                open_id_connect_url=security_scheme.open_id_connect_url,
                description=security_scheme.description,
            )
        raise AssertionError("Unsupported OpenAPI security scheme.")

    @classmethod
    def _build_litestar_oauth_flows(cls, oauth_flows: OpenApiOAuthFlows) -> openapi.spec.OAuthFlows:
        flows = {
            "implicit": cls._build_litestar_oauth_flow(oauth_flows.implicit),
            "password": cls._build_litestar_oauth_flow(object.__getattribute__(oauth_flows, "resource_owner")),
            "client_credentials": cls._build_litestar_oauth_flow(oauth_flows.client_credentials),
            "authorization_code": cls._build_litestar_oauth_flow(oauth_flows.authorization_code),
        }
        return openapi.spec.OAuthFlows(**flows)

    @classmethod
    def _build_litestar_oauth_flow(cls, oauth_flow: OpenApiOAuthFlow | None) -> openapi.spec.OAuthFlow | None:
        if oauth_flow is None:
            return None
        return openapi.spec.OAuthFlow(
            authorization_url=oauth_flow.authorization_url,
            token_url=oauth_flow.token_url,
            refresh_url=oauth_flow.refresh_url,
            scopes=oauth_flow.scopes,
        )


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


def build_span_name(method: str, route: str) -> str:
    if not route:
        return method
    return f"{method} {route}"


def build_litestar_route_details_from_scope(
    scope: Scope,
) -> tuple[str, dict[str, str]]:
    """Retrieve the span name and attributes from the ASGI scope for Litestar routes.

    Args:
        scope: The ASGI scope instance.

    Returns:
        A tuple of the span name and a dict of attrs.

    """
    path_template: typing.Final = scope.get("path_template")
    method: typing.Final = str(scope.get("method", "HTTP")).strip()
    if path_template is not None:
        path_template_stripped: typing.Final = path_template.strip()
        return build_span_name(method, path_template_stripped), {"http.route": path_template_stripped}

    path: typing.Final = scope.get("path")
    if path is not None:
        path_stripped: typing.Final = path.strip()
        return build_span_name(method, path_stripped), {"http.route": path_stripped}
    return method, {}


class LitestarOpenTelemetryInstrumentationMiddleware(ASGIMiddleware):
    def __init__(self, config: OpenTelemetryConfig) -> None:
        self.config = config

    def create_open_telemetry_middleware(self, app: ASGIApp) -> OpenTelemetryMiddleware:
        return OpenTelemetryMiddleware(
            app=app,
            client_request_hook=self.config.client_request_hook_handler,
            client_response_hook=self.config.client_response_hook_handler,
            default_span_details=build_litestar_route_details_from_scope,
            excluded_urls=get_excluded_urls(self.config.exclude_urls_env_key),
            meter=self.config.meter,
            meter_provider=self.config.meter_provider,
            server_request_hook=self.config.server_request_hook_handler,
            tracer_provider=self.config.tracer_provider,
        )

    async def handle(self, scope: Scope, receive: Receive, send: Send, next_app: ASGIApp) -> None:
        await self.create_open_telemetry_middleware(next_app)(scope, receive, send)  # type: ignore[arg-type]


@LitestarBootstrapper.use_instrument()
class LitestarOpentelemetryInstrument(OpentelemetryInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "middleware": [
                LitestarOpenTelemetryInstrumentationMiddleware(
                    LitestarOpentelemetryConfig(
                        tracer_provider=self.tracer_provider,
                        middleware_class=LitestarOpenTelemetryInstrumentationMiddleware,  # type: ignore[arg-type]
                    )
                )
            ]
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

        return {
            "route_handlers": [LitestarPrometheusController],
            "middleware": [litestar_prometheus_config.middleware],
        }

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
