from __future__ import annotations
import dataclasses
import typing

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus_remote_write import PrometheusRemoteWriteMetricsExporter
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore[attr-defined]  # noqa: TCH002
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk import resources
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider

from microbootstrap.base.base import BootstrapServicesBootstrapper, Settings_contra


if typing.TYPE_CHECKING:
    from microbootstrap.settings.base import BootstrapSettings
    from microbootstrap.settings.litestar import LitestarBootstrapSettings


@dataclasses.dataclass()
class OpenTelemetryInstrumentor:
    instrumentor: BaseInstrumentor
    additional_params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass()
class OpenTelemetryPrometheusIntegrationBootstrapper(BootstrapServicesBootstrapper["BootstrapSettings"]):
    endpoint: str | None = None
    basic_auth: dict[str, str | int | bytes] = dataclasses.field(default_factory=dict)
    headers: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    timeout: int = dataclasses.field(default=30)
    proxies: dict[str, str] = dataclasses.field(default_factory=dict)
    tls_config: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    resource: resources.Resource | None = dataclasses.field(init=False)

    def load_parameters(self, settings: BootstrapSettings | None = None) -> None:
        if not settings:
            return

        self.endpoint = settings.prometheus_endpoint
        self.basic_auth = settings.prometheus_basic_auth
        self.headers = settings.prometheus_headers
        self.timeout = settings.prometheus_timeout
        self.proxies = settings.prometheus_proxies
        self.tls_config = settings.prometheus_tls_config

    def initialize(self) -> None:
        if not self.ready:
            return

        # Metrics from instrumentors will be exported to Prometheus
        prometheus_metrics_exporter = PrometheusRemoteWriteMetricsExporter(
            endpoint=self.endpoint,  # type: ignore[arg-type]
            basic_auth=self.basic_auth,
            headers=self.headers,
            timeout=self.timeout,
            tls_config=self.tls_config,
            proxies=self.proxies,
        )

        metric_reader = PeriodicExportingMetricReader(exporter=prometheus_metrics_exporter)
        meter_provider = MeterProvider(resource=self.resource, metric_readers=[metric_reader])  # type: ignore[arg-type]
        set_meter_provider(meter_provider)

    def teardown(self) -> None:
        pass

    @property
    def ready(self) -> bool:
        return bool(self.resource and self.endpoint)


@dataclasses.dataclass()
class OpenTelemetryBootstrapper(BootstrapServicesBootstrapper[Settings_contra]):
    endpoint: str | None = None
    namespace: str | None = None
    service_name: str | None = None
    service_version: str | None = None
    container_name: str | None = None
    instruments: list[OpenTelemetryInstrumentor] = dataclasses.field(default_factory=list)
    prometheus_integration_bootstrapper: OpenTelemetryPrometheusIntegrationBootstrapper = dataclasses.field(
        default_factory=OpenTelemetryPrometheusIntegrationBootstrapper,
    )
    add_system_metrics: bool = dataclasses.field(default=False)
    sdk_language: str = dataclasses.field(default="python")

    tracer_provider: TracerProvider | None = dataclasses.field(init=False)

    def load_parameters(self, settings: Settings_contra | None = None) -> None:
        if not settings:
            return

        self.endpoint = settings.opentelemetry_endpoint
        self.namespace = settings.namespace
        self.service_name = settings.service_name
        self.service_version = settings.service_version
        self.container_name = settings.container_name

        self.instruments = settings.opentelemetry_instruments
        self.add_system_metrics = settings.opentelemetry_add_system_metrics

        self.prometheus_integration_bootstrapper.load_parameters(settings=settings)

    def initialize(self) -> None:
        if not self.ready:
            return

        resource = resources.Resource.create(
            attributes={
                resources.SERVICE_NAME: self.service_name,  # type: ignore[dict-item]
                resources.TELEMETRY_SDK_LANGUAGE: self.sdk_language,
                "namespace": self.namespace,  # type: ignore[dict-item]
                resources.SERVICE_VERSION: self.service_version,  # type: ignore[dict-item]
                resources.CONTAINER_NAME: self.container_name,  # type: ignore[dict-item]
            },
        )

        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=self.endpoint,
                    insecure=True,
                ),
            ),
        )

        if self.prometheus_integration_bootstrapper:
            self.prometheus_integration_bootstrapper.resource = resource
            self.prometheus_integration_bootstrapper.initialize()

        # Add system metrics(CPU, Network, GC and etc)
        if self.add_system_metrics:
            self.instruments.append(OpenTelemetryInstrumentor(instrumentor=SystemMetricsInstrumentor()))

        for instrumentor_with_params in self.instruments:
            instrumentor_with_params.instrumentor.instrument(
                tracer_provider=self.tracer_provider,
                **instrumentor_with_params.additional_params,
            )

        set_tracer_provider(self.tracer_provider)

    def teardown(self) -> None:
        for instrumentor_with_params in self.instruments:
            instrumentor_with_params.instrumentor.uninstrument()

        self.prometheus_integration_bootstrapper.teardown()

    @property
    def ready(self) -> bool:
        return all(
            [
                self.endpoint,
                self.namespace,
                self.service_name,
                self.service_version,
                self.container_name,
            ],
        )


@dataclasses.dataclass()
class LitestarOpenTelemetryBootstrapper(OpenTelemetryBootstrapper["LitestarBootstrapSettings"]):
    exclude_urls: list[str] = dataclasses.field(default_factory=lambda: ["/health"])

    def load_parameters(self, settings: LitestarBootstrapSettings | None = None) -> None:
        if not settings:
            return

        super().load_parameters(settings=settings)
        self.exclude_urls = settings.opentelemetry_exclude_urls
