from __future__ import annotations
import dataclasses
import typing

import litestar
import sentry_sdk
from litestar.config.app import AppConfig
from litestar.contrib import prometheus
from litestar.contrib.opentelemetry.config import OpenTelemetryConfig
from litestar.exceptions.http_exceptions import ClientException

from microbootstrap.helpers import base
from microbootstrap.helpers.logging.litestar import LitestarLoggingBootstrapper
from microbootstrap.helpers.opentelemetry import LitestarOpenTelemetryBootstrapper
from microbootstrap.helpers.sentry import SentryBootstrapper
from microbootstrap.middlewares.litestar import build_litestar_logging_middleware
from microbootstrap.middlewares.opentelemetry import OpenTelemetryMiddlware
from microbootstrap.settings.litestar import LitestarBootstrapSettings


if typing.TYPE_CHECKING:
    import litestar.types
    from litestar.logging.config import BaseLoggingConfig


async def sentry_exception_catcher_hook(
    exception: Exception,
    _request_scope: litestar.types.Scope,
) -> None:
    if isinstance(exception, ClientException):
        return
    sentry_sdk.capture_exception(exception)


def construct_teardown_opentelemetry(
    open_telemetry_bootstrapper: LitestarOpenTelemetryBootstrapper,
) -> typing.Callable[[litestar.Litestar], None]:
    def teardown_opentelemetry_hook(_litestar_application: litestar.Litestar) -> None:
        open_telemetry_bootstrapper.teardown()

    return teardown_opentelemetry_hook


@dataclasses.dataclass()
class LitestarPrometheusBootstrapper(base.BootstrapServicesBootstrapper[LitestarBootstrapSettings]):
    controller: type[prometheus.PrometheusController] | None = None
    config: prometheus.PrometheusConfig | None = None

    def load_parameters(self, settings: LitestarBootstrapSettings | None = None) -> None:
        if not settings:
            return

        self.controller = settings.prometheus_controller
        self.config = settings.prometheus_config

    def initialize(self) -> None:
        pass

    def teardown(self) -> None:
        pass

    @property
    def ready(self) -> bool:
        return bool(self.controller or self.config)


@dataclasses.dataclass()
class LitestarBootstrapper(
    base.BootstrapWebFrameworkBootstrapper[None, LitestarBootstrapSettings, AppConfig],
):
    debug: bool = dataclasses.field(default=False, init=False)
    middleware: list[litestar.types.Middleware] = dataclasses.field(default_factory=list, init=False)
    logging_config: BaseLoggingConfig | litestar.types.EmptyType | None = dataclasses.field(init=False)
    on_shutdown: list[litestar.types.LifespanHook] = dataclasses.field(default_factory=list, init=False)
    after_exception: list[litestar.types.AfterExceptionHookHandler[typing.Any]] = dataclasses.field(
        default_factory=list,
        init=False,
    )
    route_handlers: list[litestar.types.ControllerRouterHandler] = dataclasses.field(default_factory=list, init=False)
    prometheus_bootstrapper: LitestarPrometheusBootstrapper = dataclasses.field(
        default_factory=LitestarPrometheusBootstrapper,
    )
    sentry_bootstrapper: SentryBootstrapper = dataclasses.field(default_factory=SentryBootstrapper)
    logging_bootstrapper: LitestarLoggingBootstrapper = dataclasses.field(default_factory=LitestarLoggingBootstrapper)
    open_telemetry_bootstrapper: LitestarOpenTelemetryBootstrapper = dataclasses.field(
        default_factory=LitestarOpenTelemetryBootstrapper,
    )

    def load_parameters(self, app: None = None, settings: LitestarBootstrapSettings | None = None) -> None:  # noqa: ARG002
        if not settings:
            return

        self.debug = settings.debug
        self.prometheus_bootstrapper.load_parameters(settings=settings)
        self.sentry_bootstrapper.load_parameters(settings=settings)
        self.logging_bootstrapper.load_parameters(settings=settings)
        self.open_telemetry_bootstrapper.load_parameters(settings=settings)

    def initialize(self) -> AppConfig:
        self.logging_config = None
        if self.logging_bootstrapper.ready:
            self.middleware.append(
                build_litestar_logging_middleware(
                    exclude_endpoints=self.logging_bootstrapper.exclude_endpoints,
                ),
            )
            self.logging_bootstrapper.initialize()
            self.logging_config = self.logging_bootstrapper.config

        self.open_telemetry_bootstrapper.initialize()
        if self.open_telemetry_bootstrapper.ready:
            self.middleware.append(
                OpenTelemetryMiddlware(
                    OpenTelemetryConfig(
                        exclude=self.open_telemetry_bootstrapper.exclude_urls,
                        tracer_provider=self.open_telemetry_bootstrapper.tracer_provider,
                    ),
                ),
            )
            self.on_shutdown.append(construct_teardown_opentelemetry(self.open_telemetry_bootstrapper))

        if self.prometheus_bootstrapper.ready:
            if self.prometheus_bootstrapper.controller is not None:
                self.route_handlers.append(self.prometheus_bootstrapper.controller)

            if self.prometheus_bootstrapper.config is not None:
                self.middleware.append(self.prometheus_bootstrapper.config.middleware)
        else:
            self.route_handlers.append(prometheus.PrometheusController)
            self.middleware.append(prometheus.PrometheusConfig().middleware)

        self.sentry_bootstrapper.initialize()
        if self.sentry_bootstrapper.ready:
            self.after_exception.append(sentry_exception_catcher_hook)

        return AppConfig(
            debug=self.debug,
            middleware=self.middleware,
            logging_config=self.logging_config,
            on_shutdown=self.on_shutdown,
            after_exception=self.after_exception,
            route_handlers=self.route_handlers,
        )

    def teardown(self) -> None:
        self.sentry_bootstrapper.teardown()
        self.logging_bootstrapper.teardown()
        self.open_telemetry_bootstrapper.teardown()
        self.prometheus_bootstrapper.teardown()
