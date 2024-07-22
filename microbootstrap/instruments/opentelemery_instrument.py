from __future__ import annotations
import typing

import pydantic
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # noqa: TCH002
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class OpentelemetryConfig(BaseInstrumentConfig):
    service_name: str = pydantic.Field(default="micro-service")
    service_version: str = pydantic.Field(default="1.0.0")

    opentelemetry_container_name: str | None = None
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_insecure: bool = pydantic.Field(default=True)
    opentelemetry_insrumentors: list[BaseInstrumentor] = pydantic.Field(default_factory=list)
    opentelemetry_exclude_urls: list[str] = pydantic.Field(default=["/health"])


class OpentelemetryInstrument(Instrument[OpentelemetryConfig]):
    def is_ready(self) -> bool:
        return all(
            [
                self.instrument_config.opentelemetry_endpoint,
                self.instrument_config.opentelemetry_namespace,
                self.instrument_config.service_name,
                self.instrument_config.service_version,
            ],
        )

    def teardown(self) -> None:
        for instrumentor_with_params in self.instruments:
            instrumentor_with_params.instrumentor.uninstrument()

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready():
            print("Opentelemetry is not ready for bootstrapping. Provide required params.")  # noqa: T201
            return {}

        resource: typing.Final = resources.Resource.create(
            attributes={
                resources.SERVICE_NAME: self.instrument_config.service_name,
                resources.TELEMETRY_SDK_LANGUAGE: "python",
                resources.SERVICE_NAMESPACE: self.instrument_config.opentelemetry_namespace,
                resources.SERVICE_VERSION: self.instrument_config.service_version,
                resources.CONTAINER_NAME: self.instrument_config.container_name,
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
        for opentelemetry_insrumentor in self.instrument_config.opentelemetry_insrumentors:
            opentelemetry_insrumentor.instrumentor.instrument(
                tracer_provider=self.tracer_provider,
            )
        set_tracer_provider(self.tracer_provider)
        return self.bootstrap_before()

    @classmethod
    def get_config_type(cls) -> type[OpentelemetryConfig]:
        return OpentelemetryConfig
