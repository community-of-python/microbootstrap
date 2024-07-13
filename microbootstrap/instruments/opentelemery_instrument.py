from __future__ import annotations
import dataclasses
import typing

import pydantic
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from microbootstrap.instruments import Instrument


class OpentelemetryConfig(pydantic.BaseModel):
    service_name: str | None = None
    service_version: str | None = None
    container_name: str | None = None
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_add_system_metrics: bool = dataclasses.field(default=False)
    opentelemetry_insecure: bool = dataclasses.field(default=True)

    class Config:
        arbitrary_types_allowed = True


class OpentelemetryInstrument(Instrument[OpentelemetryConfig]):
    @property
    def is_ready(self) -> bool:
        return all(
            [
                self.instrument_config.opentelemetry_endpoint,
                self.instrument_config.opentelemetry_namespace,
                self.instrument_config.service_name,
                self.instrument_config.service_version,
                self.instrument_config.container_name,
            ],
        )

    def teardown(self) -> None:
        pass

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready:
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
        return self.successful_bootstrap_result
