from __future__ import annotations
import functools
import json
import typing

import prometheus_client
import sentry_sdk
import structlog
import typing_extensions
from faststream._internal.logger.logger_proxy import RealLoggerObject
from faststream.asgi import AsgiFastStream, AsgiResponse
from faststream.asgi import get as handle_get
from faststream.specification import AsyncAPI
from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
from opentelemetry.util.http import ExcludeList

from microbootstrap.bootstrappers.base import ApplicationBootstrapper
from microbootstrap.config.faststream import FastStreamConfig
from microbootstrap.instruments.health_checks_instrument import HealthChecksInstrument
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import (
    BaseOpentelemetryInstrument,
    FastStreamOpentelemetryConfig,
    build_span_name,
)
from microbootstrap.instruments.prometheus_instrument import FastStreamPrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument
from microbootstrap.middlewares.faststream import FastStreamOpenTelemetryBaggageMiddleware
from microbootstrap.settings import FastStreamSettings


if typing.TYPE_CHECKING:
    from faststream.asgi.types import ASGIApp, Receive, Scope, Send


MessageT = typing.TypeVar("MessageT")
ResponseT = typing.TypeVar("ResponseT")


def _with_sentry_isolation_scope(
    process_message: typing.Callable[[MessageT], typing.Awaitable[ResponseT]],
) -> typing.Callable[[MessageT], typing.Awaitable[ResponseT]]:
    @functools.wraps(process_message)
    async def isolated_process_message(message: MessageT) -> ResponseT:
        with sentry_sdk.isolation_scope():
            return await process_message(message)

    return isolated_process_message


def _isolate_faststream_subscribers(application: AsgiFastStream) -> None:
    for broker in application.brokers:
        for subscriber in broker.subscribers:
            object.__setattr__(
                subscriber,
                "process_message",
                _with_sentry_isolation_scope(subscriber.process_message),
            )


class KwargsAsgiFastStream(AsgiFastStream):
    def __init__(self, **kwargs: typing.Any) -> None:  # noqa: ANN401
        # `broker` argument is positional-only
        super().__init__(kwargs.pop("broker", None), **kwargs)
        self.http_app: ASGIApp = super().__call__

    def add_http_middleware(self, build_middleware: typing.Callable[[ASGIApp], ASGIApp]) -> None:
        self.http_app = build_middleware(self.http_app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Lifespan and websocket scopes bypass HTTP middlewares
        if scope["type"] == "http":
            await self.http_app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def build_faststream_route_details_from_scope(scope: Scope) -> tuple[str, dict[str, str]]:
    """Retrieve the span name and attributes from the ASGI scope for FastStream routes.

    FastStream matches ASGI routes by exact path, so the request path is the route itself.
    """
    method: typing.Final = str(scope.get("method", "HTTP")).strip()
    path: typing.Final = scope.get("path")
    if path is None:
        return method, {}
    path_stripped: typing.Final = path.strip()
    return build_span_name(method, path_stripped), {"http.route": path_stripped}


class FastStreamBootstrapper(ApplicationBootstrapper[FastStreamSettings, AsgiFastStream, FastStreamConfig]):
    application_config = FastStreamConfig()
    application_type = KwargsAsgiFastStream

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        return {
            "specification": AsyncAPI(
                title=self.settings.service_name,
                version=self.settings.service_version,
                description=self.settings.service_description,
            ),
            "on_shutdown": [self.teardown],
            "on_startup": [self.console_writer.print_bootstrap_table],
            "asyncapi_path": self.settings.asyncapi_path,
        }


@FastStreamBootstrapper.use_instrument()
class FastStreamSentryInstrument(SentryInstrument):
    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        # FastStream logs handler errors after custom broker middlewares exit, so the isolation scope
        # must enclose the subscriber's complete processing lifecycle.
        if application.brokers:
            _isolate_faststream_subscribers(application)
        else:
            application.on_startup(functools.partial(_isolate_faststream_subscribers, application))
        return application


FastStreamBootstrapper.use_instrument()(PyroscopeInstrument)


@FastStreamBootstrapper.use_instrument()
class FastStreamOpentelemetryInstrument(BaseOpentelemetryInstrument[FastStreamOpentelemetryConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.opentelemetry_middleware_cls and super().is_ready())

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if self.instrument_config.opentelemetry_middleware_cls and application.broker:
            application.broker.add_middleware(
                self.instrument_config.opentelemetry_middleware_cls(tracer_provider=self.tracer_provider),
            )
            application.broker.add_middleware(
                FastStreamOpenTelemetryBaggageMiddleware(
                    baggage_span_attributes=self.instrument_config.opentelemetry_baggage_span_attributes,
                ),
            )
        if isinstance(application, KwargsAsgiFastStream):
            application.add_http_middleware(self.create_open_telemetry_middleware)
        return application

    def create_open_telemetry_middleware(self, app: ASGIApp) -> ASGIApp:
        return OpenTelemetryMiddleware(
            app=app,
            default_span_details=build_faststream_route_details_from_scope,
            excluded_urls=ExcludeList(self.define_exclude_urls()),
            tracer_provider=self.tracer_provider,
        )

    @classmethod
    def get_config_type(cls) -> type[FastStreamOpentelemetryConfig]:
        return FastStreamOpentelemetryConfig


faststream_app_logger: typing.Final = structlog.get_logger("microbootstrap.faststream.app")
faststream_broker_logger: typing.Final = structlog.get_logger("microbootstrap.faststream.broker")


@FastStreamBootstrapper.use_instrument()
class FastStreamLoggingInstrument(LoggingInstrument):
    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {"logger": faststream_app_logger}

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        for one_broker in application.brokers:
            one_broker.config.broker_config.logger.logger = RealLoggerObject(faststream_broker_logger)
        return application


@FastStreamBootstrapper.use_instrument()
class FastStreamPrometheusInstrument(PrometheusInstrument[FastStreamPrometheusConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_middleware_cls and super().is_ready())

    def bootstrap_before(self) -> dict[str, typing.Any]:
        return {
            "asgi_routes": (
                (
                    self.instrument_config.prometheus_metrics_path,
                    prometheus_client.make_asgi_app(prometheus_client.REGISTRY),
                ),
            ),
        }

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        if self.instrument_config.prometheus_middleware_cls and application.broker:
            application.broker.add_middleware(
                self.instrument_config.prometheus_middleware_cls(
                    registry=prometheus_client.REGISTRY,
                    custom_labels=self.instrument_config.prometheus_custom_labels,
                ),
            )
        return application

    @classmethod
    def get_config_type(cls) -> type[FastStreamPrometheusConfig]:
        return FastStreamPrometheusConfig


@FastStreamBootstrapper.use_instrument()
class FastStreamHealthChecksInstrument(HealthChecksInstrument):
    def bootstrap(self) -> None: ...
    def bootstrap_before(self) -> dict[str, typing.Any]:
        @handle_get
        async def check_health(scope: typing.Any) -> AsgiResponse:  # noqa: ANN401, ARG001
            return (
                AsgiResponse(
                    json.dumps(self.render_health_check_data()).encode(),
                    200,
                    headers={"content-type": "text/plain"},
                )
                if await self.define_health_status()
                else AsgiResponse(b"Service is unhealthy", 500, headers={"content-type": "application/json"})
            )

        return {"asgi_routes": ((self.instrument_config.health_checks_path, check_health),)}

    async def define_health_status(self) -> bool:
        return await self.application.broker.ping(timeout=5) if self.application and self.application.broker else False

    def bootstrap_after(self, application: AsgiFastStream) -> AsgiFastStream:  # type: ignore[override]
        self.application = application
        return application
