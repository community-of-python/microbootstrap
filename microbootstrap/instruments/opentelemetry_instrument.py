from __future__ import annotations
import dataclasses
import os
import threading
import typing

import pydantic
import structlog
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.dependencies import DependencyConflictError
from opentelemetry.instrumentation.environment_variables import OTEL_PYTHON_DISABLED_INSTRUMENTATIONS
from opentelemetry.instrumentation.instrumentor import BaseInstrumentor  # type: ignore[attr-defined] # noqa: TC002
from opentelemetry.sdk import resources
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace import TracerProvider as SdkTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.trace import format_span_id, set_tracer_provider
from opentelemetry.util._importlib_metadata import entry_points

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


LOGGER_OBJ: typing.Final = structlog.get_logger(__name__)


try:
    import pyroscope  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pyroscope = None


if typing.TYPE_CHECKING:
    import faststream
    from opentelemetry.context import Context
    from opentelemetry.metrics import Meter, MeterProvider
    from opentelemetry.trace import TracerProvider


OpentelemetryConfigT = typing.TypeVar("OpentelemetryConfigT", bound="OpentelemetryConfig")


@dataclasses.dataclass()
class OpenTelemetryInstrumentor:
    instrumentor: BaseInstrumentor
    additional_params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)


class OpentelemetryConfig(BaseInstrumentConfig):
    service_debug: bool = True
    service_name: str = "micro-service"
    service_version: str = "1.0.0"
    health_checks_path: str = "/health/"
    pyroscope_endpoint: pydantic.HttpUrl | None = None

    opentelemetry_service_name: str | None = None
    opentelemetry_container_name: str | None = pydantic.Field(os.environ.get("HOSTNAME") or None)
    opentelemetry_endpoint: str | None = None
    opentelemetry_namespace: str | None = None
    opentelemetry_insecure: bool = pydantic.Field(default=True)
    opentelemetry_instrumentors: list[OpenTelemetryInstrumentor] = pydantic.Field(default_factory=list)
    opentelemetry_exclude_urls: list[str] = pydantic.Field(default=["/metrics"])
    opentelemetry_disabled_instrumentations: list[str] = pydantic.Field(
        default=[
            one_package_to_exclude.strip()
            for one_package_to_exclude in os.environ.get(OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, "").split(",")
        ]
    )
    opentelemetry_log_traces: bool = False


@typing.runtime_checkable
class FastStreamTelemetryMiddlewareProtocol(typing.Protocol):
    def __init__(
        self,
        *,
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        meter: Meter | None = None,
    ) -> None: ...
    def __call__(self, msg: typing.Any | None) -> faststream.BaseMiddleware: ...  # noqa: ANN401


class FastStreamOpentelemetryConfig(OpentelemetryConfig):
    opentelemetry_middleware_cls: type[FastStreamTelemetryMiddlewareProtocol] | None = None


def _format_span(readable_span: ReadableSpan) -> str:
    return typing.cast("str", readable_span.to_json(indent=None)) + os.linesep


class BaseOpentelemetryInstrument(Instrument[OpentelemetryConfigT]):
    instrument_name = "Opentelemetry"
    ready_condition = "Provide all necessary config parameters"

    def _load_instrumentors(self) -> None:
        for entry_point in entry_points(group="opentelemetry_instrumentor"):  # type: ignore[no-untyped-call]
            if entry_point.name in self.instrument_config.opentelemetry_disabled_instrumentations:
                continue

            try:
                entry_point.load()().instrument(tracer_provider=self.tracer_provider)
            except DependencyConflictError as exc:
                LOGGER_OBJ.debug("Skipping instrumentation", entry_point_name=entry_point.name, reason=exc.conflict)
                continue
            except ModuleNotFoundError:
                continue
            except ImportError:
                LOGGER_OBJ.debug("Importing failed, skipping it", entry_point_name=entry_point.name)
                continue
            except Exception:
                LOGGER_OBJ.debug("Instrumenting failed", entry_point_name=entry_point.name)
                raise

    def is_ready(self) -> bool:
        return (
            bool(self.instrument_config.opentelemetry_endpoint)
            or self.instrument_config.service_debug
            or self.instrument_config.opentelemetry_log_traces
        )

    def teardown(self) -> None:
        for instrumentor_with_params in self.instrument_config.opentelemetry_instrumentors:
            instrumentor_with_params.instrumentor.uninstrument(**instrumentor_with_params.additional_params)

    def bootstrap(self) -> None:
        attributes = {
            ResourceAttributes.SERVICE_NAME: self.instrument_config.opentelemetry_service_name
            or self.instrument_config.service_name,
            ResourceAttributes.TELEMETRY_SDK_LANGUAGE: "python",
            ResourceAttributes.SERVICE_VERSION: self.instrument_config.service_version,
        }
        if self.instrument_config.opentelemetry_namespace:
            attributes[ResourceAttributes.SERVICE_NAMESPACE] = self.instrument_config.opentelemetry_namespace
        if self.instrument_config.opentelemetry_container_name:
            attributes[ResourceAttributes.CONTAINER_NAME] = self.instrument_config.opentelemetry_container_name
        resource: typing.Final = resources.Resource.create(attributes=attributes)

        self.tracer_provider = SdkTracerProvider(resource=resource)
        if self.instrument_config.pyroscope_endpoint and pyroscope:
            self.tracer_provider.add_span_processor(PyroscopeSpanProcessor())

        if self.instrument_config.opentelemetry_log_traces:
            self.tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter(formatter=_format_span)))
        if self.instrument_config.opentelemetry_endpoint:
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
        self._load_instrumentors()
        set_tracer_provider(self.tracer_provider)


class OpentelemetryInstrument(BaseOpentelemetryInstrument[OpentelemetryConfig]):
    def define_exclude_urls(self) -> list[str]:
        exclude_urls = [*self.instrument_config.opentelemetry_exclude_urls]
        if self.instrument_config.health_checks_path and self.instrument_config.health_checks_path not in exclude_urls:
            exclude_urls.append(self.instrument_config.health_checks_path)
        return exclude_urls

    @classmethod
    def get_config_type(cls) -> type[OpentelemetryConfig]:
        return OpentelemetryConfig


OTEL_PROFILE_ID_KEY: typing.Final = "pyroscope.profile.id"
PYROSCOPE_SPAN_ID_KEY: typing.Final = "span_id"
PYROSCOPE_SPAN_NAME_KEY: typing.Final = "span_name"


def _is_root_span(span: ReadableSpan) -> bool:
    return span.parent is None or span.parent.is_remote


# Extended `pyroscope-otel` span processor: https://github.com/grafana/otel-profiling-python/blob/990662d416943e992ab70036b35b27488c98336a/src/pyroscope/otel/__init__.py
# Includes `span_name` to identify if it makes sense to go to profiles from traces.
class PyroscopeSpanProcessor(SpanProcessor):
    def on_start(self, span: Span, parent_context: Context | None = None) -> None:  # noqa: ARG002
        if _is_root_span(span):
            formatted_span_id = format_span_id(span.context.span_id)
            thread_id = threading.get_ident()

            span.set_attribute(OTEL_PROFILE_ID_KEY, formatted_span_id)
            pyroscope.add_thread_tag(thread_id, PYROSCOPE_SPAN_ID_KEY, formatted_span_id)
            pyroscope.add_thread_tag(thread_id, PYROSCOPE_SPAN_NAME_KEY, span.name)

    def on_end(self, span: ReadableSpan) -> None:
        if _is_root_span(span):
            thread_id = threading.get_ident()
            pyroscope.remove_thread_tag(thread_id, PYROSCOPE_SPAN_ID_KEY, format_span_id(span.context.span_id))
            pyroscope.remove_thread_tag(thread_id, PYROSCOPE_SPAN_NAME_KEY, span.name)

    def force_flush(self, timeout_millis: int = 30000) -> bool:  # noqa: ARG002  # pragma: no cover
        return True
