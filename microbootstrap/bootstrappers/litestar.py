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
    OpenApiSecurityScheme,
)
from microbootstrap.instruments.openapi_version_docs import (
    OpenApiVersionDocsConfig,
    append_version_documentation,
    build_accept_versioning_extension,
    get_supported_versions,
    is_operation_suppressed,
)
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
        version_docs_config: typing.Final = self.instrument_config.openapi_version_docs
        security_schemes: typing.Final = self.instrument_config.security_schemes
        if (
            (version_docs_config is None or not version_docs_config.enabled) and not security_schemes
        ) or application.openapi_schema is None:
            return application
        expected_schemes: dict[str, openapi.spec.SecurityScheme] | None = None
        if security_schemes:
            expected_schemes = prepare_security_schemes(application.openapi_schema, security_schemes)
        version_documentation: list[tuple[openapi.spec.PathItem, str, openapi.spec.Operation]] = []
        if version_docs_config is not None and version_docs_config.enabled:
            version_documentation = prepare_version_documentation(application.openapi_schema, version_docs_config)
        if expected_schemes is not None:
            apply_security_schemes(application.openapi_schema, expected_schemes)
        apply_version_documentation(version_documentation)
        return application


def add_security_schemes(
    openapi_schema: openapi.spec.OpenAPI,
    configured_schemes: typing.Mapping[str, OpenApiSecurityScheme],
) -> None:
    apply_security_schemes(openapi_schema, prepare_security_schemes(openapi_schema, configured_schemes))


def prepare_security_schemes(
    openapi_schema: openapi.spec.OpenAPI,
    configured_schemes: typing.Mapping[str, OpenApiSecurityScheme],
) -> dict[str, openapi.spec.SecurityScheme]:
    expected_schemes: typing.Final = {
        scheme_name: build_litestar_security_scheme(security_scheme)
        for scheme_name, security_scheme in configured_schemes.items()
    }
    security_schemes = openapi_schema.components.security_schemes
    if security_schemes is None:
        return expected_schemes

    for scheme_name, expected_scheme in expected_schemes.items():
        existing_scheme = security_schemes.get(scheme_name)
        if existing_scheme is not None and (
            not isinstance(existing_scheme, openapi.spec.SecurityScheme)
            or existing_scheme.to_schema() != expected_scheme.to_schema()
        ):
            message = f"OpenAPI security scheme '{scheme_name}' conflicts with the configured security scheme."
            raise ValueError(message)
    return expected_schemes


def apply_security_schemes(
    openapi_schema: openapi.spec.OpenAPI,
    expected_schemes: dict[str, openapi.spec.SecurityScheme],
) -> None:
    security_schemes = openapi_schema.components.security_schemes
    if security_schemes is None:
        openapi_schema.components.security_schemes = typing.cast(
            "dict[str, openapi.spec.SecurityScheme | openapi.spec.Reference]",
            expected_schemes,
        )
        return
    security_schemes.update({name: scheme for name, scheme in expected_schemes.items() if name not in security_schemes})


def prepare_version_documentation(
    openapi_schema: openapi.spec.OpenAPI,
    configuration: OpenApiVersionDocsConfig,
) -> list[tuple[openapi.spec.PathItem, str, openapi.spec.Operation]]:
    updates: list[tuple[openapi.spec.PathItem, str, openapi.spec.Operation]] = []
    if openapi_schema.paths is None:
        return updates
    for path, path_item in openapi_schema.paths.items():
        if not isinstance(path_item, openapi.spec.PathItem):
            continue
        for method in ("delete", "get", "head", "options", "patch", "post", "put", "trace"):
            operation = getattr(path_item, method)
            if operation is None or is_operation_suppressed(configuration, path, method):
                continue
            if operation.description is not None and not isinstance(operation.description, str):
                message = f"OpenAPI operation {method.upper()} {path} has a non-string description."
                raise ValueError(message)
            supported_versions = get_supported_versions(configuration, path, method)
            extension = build_accept_versioning_extension(configuration, supported_versions)
            description = append_version_documentation(operation.description, configuration, supported_versions)
            documented_operation = add_accept_versioning_extension(operation, extension)
            if documented_operation is operation:
                if description == operation.description:
                    continue
                documented_operation = copy_operation(operation)
            object.__setattr__(documented_operation, "description", description)
            updates.append((path_item, method, documented_operation))
    return updates


def apply_version_documentation(
    updates: typing.Iterable[tuple[openapi.spec.PathItem, str, openapi.spec.Operation]],
) -> None:
    for path_item, method, operation in updates:
        setattr(path_item, method, operation)


def build_litestar_security_scheme(security_scheme: OpenApiSecurityScheme) -> openapi.spec.SecurityScheme:
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
            flows=build_litestar_oauth_flows(security_scheme.flows),
            description=security_scheme.description,
        )
    if isinstance(security_scheme, OpenApiOpenIdConnectSecurityScheme):
        return openapi.spec.SecurityScheme(
            type=security_scheme.type,
            open_id_connect_url=security_scheme.open_id_connect_url,
            description=security_scheme.description,
        )
    raise AssertionError("Unsupported OpenAPI security scheme.")


def build_litestar_oauth_flows(oauth_flows: OpenApiOAuthFlows) -> openapi.spec.OAuthFlows:
    flow_arguments: typing.Final[dict[str, typing.Any]] = {
        "implicit": build_litestar_oauth_flow(oauth_flows.implicit),
        "password": build_litestar_oauth_flow(oauth_flows.resource_owner),
        "client_credentials": build_litestar_oauth_flow(oauth_flows.client_credentials),
        "authorization_code": build_litestar_oauth_flow(oauth_flows.authorization_code),
    }
    return openapi.spec.OAuthFlows(**flow_arguments)


def build_litestar_oauth_flow(oauth_flow: OpenApiOAuthFlow | None) -> openapi.spec.OAuthFlow | None:
    if oauth_flow is None:
        return None
    return openapi.spec.OAuthFlow(
        authorization_url=oauth_flow.authorization_url,
        token_url=oauth_flow.token_url,
        refresh_url=oauth_flow.refresh_url,
        scopes=oauth_flow.scopes,
    )


def add_accept_versioning_extension(
    operation: openapi.spec.Operation,
    expected_extension: dict[str, str | list[str]],
) -> openapi.spec.Operation:
    extension_name: typing.Final = "x-accept-versioning"
    for field in dataclasses.fields(operation):
        if field.metadata.get("alias") != extension_name:
            continue
        existing_extension = getattr(operation, field.name)
        if existing_extension is None:
            versioned_operation = copy_operation(operation)
            object.__setattr__(versioned_operation, field.name, expected_extension)
            return versioned_operation
        if existing_extension != expected_extension:
            message = f"OpenAPI operation {extension_name} conflicts with configured Accept version documentation."
            raise ValueError(message)
        return operation

    operation_type = typing.cast(
        "type[openapi.spec.Operation]",
        dataclasses.make_dataclass(
            cls_name=f"{type(operation).__name__}WithAcceptVersioning",
            fields=[
                (
                    "accept_versioning",
                    dict[str, str | list[str]] | None,
                    dataclasses.field(default=None, metadata={"alias": extension_name}),
                )
            ],
            bases=(type(operation),),
        ),
    )
    versioned_operation = copy_operation(operation, operation_type)
    object.__setattr__(versioned_operation, "accept_versioning", expected_extension)
    return versioned_operation


def copy_operation(
    operation: openapi.spec.Operation,
    operation_type: type[openapi.spec.Operation] | None = None,
) -> openapi.spec.Operation:
    copied_operation = object.__new__(operation_type or type(operation))
    copy_instance_state(operation, copied_operation)
    return copied_operation


def copy_instance_state(source: object, target: object) -> None:
    source_dict = getattr(source, "__dict__", None)
    target_dict = getattr(target, "__dict__", None)
    if isinstance(source_dict, dict) and isinstance(target_dict, dict):
        target_dict.update(source_dict)

    for source_class in type(source).__mro__:
        slot_names = source_class.__dict__.get("__slots__", ())
        if isinstance(slot_names, str):
            slot_names = (slot_names,)
        for slot_name in slot_names:
            if slot_name in {"__dict__", "__weakref__"} or not hasattr(source, slot_name):
                continue
            object.__setattr__(target, slot_name, getattr(source, slot_name))


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
