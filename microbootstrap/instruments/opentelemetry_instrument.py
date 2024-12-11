from __future__ import annotations
import dataclasses
import typing

import pydantic
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore[attr-defined] # noqa: TC002
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


@dataclasses.dataclass()
class OpenTelemetryInstrumentor:
    instrumentor: BaseInstrumentor
    additional_params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)


class OpentelemetryConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_version: str = "1.0.0"

    opentelemetry_service_name: str | None = None
    opentelemetry_container_name: str | None = None
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_insecure: bool = pydantic.Field(default=True)
    opentelemetry_instrumentors: list[OpenTelemetryInstrumentor] = pydantic.Field(default_factory=list)
    opentelemetry_exclude_urls: list[str] = pydantic.Field(default=[])


class OpentelemetryInstrument(Instrument[OpentelemetryConfig]):
    instrument_name = "Opentelemetry"
    ready_condition = "Provide all necessary config parameters"

    def is_ready(self) -> bool:
        return all(
            [
                self.instrument_config.opentelemetry_endpoint,
                self.instrument_config.opentelemetry_namespace,
                self.instrument_config.service_name,
                self.instrument_config.service_version,
                self.instrument_config.opentelemetry_container_name,
            ],
        )

    def teardown(self) -> None:
        for instrumentor_with_params in self.instrument_config.opentelemetry_instrumentors:
            instrumentor_with_params.instrumentor.uninstrument(**instrumentor_with_params.additional_params)

    def bootstrap(self) -> None:
        resource: typing.Final = resources.Resource.create(
            attributes={
                resources.SERVICE_NAME: self.instrument_config.opentelemetry_service_name
                or self.instrument_config.service_name,
                resources.TELEMETRY_SDK_LANGUAGE: "python",
                resources.SERVICE_NAMESPACE: self.instrument_config.opentelemetry_namespace,  # type: ignore[dict-item]
                resources.SERVICE_VERSION: self.instrument_config.service_version,
                resources.CONTAINER_NAME: self.instrument_config.opentelemetry_container_name,  # type: ignore[dict-item]
            },
        )

        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(
                    endpoint=self.instrument_config.opentelemetry_endpoint,
                    insecure=self.instrument_config.opentelemetry_insecure,
                ),
            ),
        )
        for opentelemetry_instrumentor in self.instrument_config.opentelemetry_instrumentors:
            opentelemetry_instrumentor.instrumentor.instrument(
                tracer_provider=self.tracer_provider,
                **opentelemetry_instrumentor.additional_params,
            )

    @classmethod
    def get_config_type(cls) -> type[OpentelemetryConfig]:
        return OpentelemetryConfig
