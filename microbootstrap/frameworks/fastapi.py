from __future__ import annotations
import dataclasses
import typing

import fastapi
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_fastapi_instrumentator import PrometheusFastApiInstrumentator  # type: ignore[attr-defined]
from sentry_sdk.integrations.fastapi import FastApiIntegration

from microbootstrap.helpers.base import BootstrapWebFrameworkBootstrapper
from microbootstrap.helpers.logging.base import LoggingBootstrapper
from microbootstrap.helpers.opentelemetry import OpenTelemetryBootstrapper
from microbootstrap.helpers.sentry import SentryBootstrapper
from microbootstrap.middlewares.fastapi import FastAPILoggingMiddleware
from microbootstrap.settings.fastapi import FastAPIBootstrapSettings


@dataclasses.dataclass()
class FastAPIBootstrapper(BootstrapWebFrameworkBootstrapper[fastapi.FastAPI, FastAPIBootstrapSettings, None]):
    app: fastapi.FastAPI | None = None
    debug: bool = dataclasses.field(default=False, init=False)
    excluded_urls: str | None = None
    enable_prometheus_instrumentator: bool = dataclasses.field(default=True)
    prometheus_instrumentator_params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    sentry_bootstrapper: SentryBootstrapper = dataclasses.field(default_factory=SentryBootstrapper)
    logging_bootstrapper: LoggingBootstrapper[FastAPIBootstrapSettings] = dataclasses.field(
        default_factory=LoggingBootstrapper,
    )
    open_telemetry_bootstrapper: OpenTelemetryBootstrapper[FastAPIBootstrapSettings] = dataclasses.field(
        default_factory=OpenTelemetryBootstrapper,
    )

    def load_parameters(self, app: fastapi.FastAPI, settings: FastAPIBootstrapSettings | None = None) -> None:
        self.app = app

        if not settings:
            return

        self.debug = settings.debug
        self.excluded_urls = settings.excluded_urls
        self.enable_prometheus_instrumentator = settings.enable_prometheus_instrumentator
        self.prometheus_instrumentator_params = settings.prometheus_instrumentator_params

        self.sentry_bootstrapper.load_parameters(settings=settings)
        self.logging_bootstrapper.load_parameters(settings=settings)
        self.open_telemetry_bootstrapper.load_parameters(settings=settings)

    def initialize(self) -> None:
        if not self.app:
            return

        self.app.debug = self.debug

        if self.logging_bootstrapper.ready:
            self.logging_bootstrapper.initialize()
            self.app.add_middleware(FastAPILoggingMiddleware)

        if not self.sentry_bootstrapper.integrations:
            self.sentry_bootstrapper.integrations = [
                FastApiIntegration(transaction_style="endpoint"),
            ]

        self.sentry_bootstrapper.initialize()
        self.open_telemetry_bootstrapper.initialize()

        if self.open_telemetry_bootstrapper.ready:
            FastAPIInstrumentor.instrument_app(
                app=self.app,
                tracer_provider=self.open_telemetry_bootstrapper.tracer_provider,
                excluded_urls=self.excluded_urls,
            )

        if self.enable_prometheus_instrumentator:
            PrometheusFastApiInstrumentator(
                **self.prometheus_instrumentator_params,
            ).instrument(
                self.app,
            ).expose(self.app, name="prometheus_metrics")

    def teardown(self) -> None:
        if not self.app:
            return

        self.sentry_bootstrapper.teardown()
        self.logging_bootstrapper.teardown()
        self.open_telemetry_bootstrapper.teardown()
        if self.open_telemetry_bootstrapper.ready:
            FastAPIInstrumentor.uninstrument_app(self.app)
