from __future__ import annotations
import contextlib
import functools
import typing
import urllib.parse
from collections.abc import Mapping

import orjson
import pydantic
import sentry_sdk
from opentelemetry import baggage
from sentry_sdk import _types as sentry_types
from sentry_sdk.integrations import Integration

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class SentryConfig(BaseInstrumentConfig):
    service_environment: str | None = None

    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_max_value_length: int = 16384
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] = pydantic.Field(default_factory=list)
    sentry_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    sentry_tags: dict[str, str] | None = None
    sentry_before_send: typing.Callable[[typing.Any, typing.Any], typing.Any | None] | None = None
    sentry_opentelemetry_trace_url_template: str | None = None
    sentry_opentelemetry_baggage_keys: set[str] = pydantic.Field(default_factory=set)
    sentry_opentelemetry_baggage_url_templates: dict[str, str] = pydantic.Field(default_factory=dict)


IGNORED_STRUCTLOG_ATTRIBUTES: typing.Final = frozenset({"event", "level", "logger", "tracing", "timestamp"})


def enrich_sentry_event_from_structlog_log(event: sentry_types.Event, _hint: sentry_types.Hint) -> sentry_types.Event:
    if (
        (logentry := event.get("logentry"))
        and (formatted_message := logentry.get("formatted"))
        and (isinstance(formatted_message, str))
        and formatted_message.startswith("{")
        and (isinstance(event.get("contexts"), dict))
    ):
        try:
            loaded_formatted_log = orjson.loads(formatted_message)
        except orjson.JSONDecodeError:
            return event
        if not isinstance(loaded_formatted_log, dict):
            return event

        if event_name := loaded_formatted_log.get("event"):
            event["logentry"]["formatted"] = event_name  # type: ignore[index]
        else:
            return event

        additional_extra = loaded_formatted_log
        for one_attr in IGNORED_STRUCTLOG_ATTRIBUTES:
            additional_extra.pop(one_attr, None)
        if additional_extra:
            event["contexts"]["structlog"] = additional_extra

    return event


SENTRY_EXTRA_OTEL_TRACE_ID_KEY: typing.Final = "otelTraceID"
SENTRY_EXTRA_OTEL_TRACE_URL_KEY: typing.Final = "otelTraceURL"
SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE: typing.Final = "__microbootstrap_sentry_opentelemetry_baggage__"


@typing.final
class SentryOpentelemetryBaggageIntegration(Integration):
    identifier = "microbootstrap_opentelemetry_baggage"

    def __init__(self, baggage_keys: set[str], baggage_url_templates: dict[str, str]) -> None:
        self.baggage_keys: typing.Final = frozenset(baggage_keys)
        self.baggage_url_templates: typing.Final = dict(baggage_url_templates)

    @staticmethod
    def setup_once() -> None:
        pass


def snapshot_sentry_opentelemetry_baggage(exception: BaseException) -> None:
    integration = sentry_sdk.get_client().get_integration(SentryOpentelemetryBaggageIntegration)
    if not isinstance(integration, SentryOpentelemetryBaggageIntegration) or hasattr(
        exception,
        SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE,
    ):
        return

    configured_keys: typing.Final = integration.baggage_keys.union(integration.baggage_url_templates)
    snapshot: typing.Final = {key: baggage.get_baggage(key) for key in configured_keys}
    with contextlib.suppress(AttributeError, TypeError):
        setattr(exception, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE, snapshot)


def _find_sentry_opentelemetry_baggage_snapshot(hint: sentry_types.Hint) -> Mapping[str, object | None] | None:
    if not isinstance(hint, Mapping):
        return None

    exc_info: typing.Final = hint.get("exc_info")
    if not isinstance(exc_info, tuple):
        return None
    try:
        _, exception_value, _ = exc_info
    except ValueError:
        return None
    if not isinstance(exception_value, BaseException):
        return None

    exceptions_to_visit: list[BaseException] = [exception_value]
    visited_exceptions: set[int] = set()
    while exceptions_to_visit:
        exception = exceptions_to_visit.pop()
        if id(exception) in visited_exceptions:
            continue
        visited_exceptions.add(id(exception))
        exception_snapshot = getattr(exception, SENTRY_OTEL_BAGGAGE_SNAPSHOT_ATTRIBUTE, None)
        if isinstance(exception_snapshot, Mapping):
            return exception_snapshot

        nested_exceptions = getattr(exception, "exceptions", ())
        if isinstance(nested_exceptions, tuple):
            exceptions_to_visit.extend(
                reversed([nested for nested in nested_exceptions if isinstance(nested, BaseException)])
            )
        if chained_exception := exception.__cause__ or (
            None if exception.__suppress_context__ else exception.__context__
        ):
            exceptions_to_visit.append(chained_exception)
    return None


def add_trace_url_to_event(
    trace_link_template: str, event: sentry_types.Event, _hint: sentry_types.Hint
) -> sentry_types.Event:
    if trace_link_template and (trace_id := event.get("extra", {}).get(SENTRY_EXTRA_OTEL_TRACE_ID_KEY)):
        event["extra"][SENTRY_EXTRA_OTEL_TRACE_URL_KEY] = trace_link_template.replace("{trace_id}", str(trace_id))
    return event


def enrich_sentry_event_from_opentelemetry_baggage(
    baggage_keys: set[str],
    baggage_url_templates: dict[str, str],
    event: sentry_types.Event,
    hint: sentry_types.Hint,
) -> sentry_types.Event:
    configured_keys: typing.Final = baggage_keys.union(baggage_url_templates)
    snapshot: typing.Final = _find_sentry_opentelemetry_baggage_snapshot(hint)
    baggage_values: typing.Final = (
        snapshot if snapshot is not None else {key: baggage.get_baggage(key) for key in configured_keys}
    )

    for key in baggage_keys:
        if (value := baggage_values.get(key)) is not None:
            event.setdefault("tags", {})[key] = str(value)
        elif tags := event.get("tags"):
            tags.pop(key, None)

    for key, url_template in baggage_url_templates.items():
        placeholder = f"{{{key}}}"
        extra_key = f"{key}_url"
        if (value := baggage_values.get(key)) is not None and placeholder in url_template:
            event.setdefault("extra", {})[extra_key] = url_template.replace(
                placeholder,
                urllib.parse.quote(str(value), safe=""),
            )
        elif extra := event.get("extra"):
            extra.pop(extra_key, None)
    return event


def wrap_before_send_callbacks(*callbacks: sentry_types.EventProcessor | None) -> sentry_types.EventProcessor:
    def run_before_send(event: sentry_types.Event, hint: sentry_types.Hint) -> sentry_types.Event | None:
        for callback in callbacks:
            if not callback:
                continue
            temp_event = callback(event, hint)
            if temp_event is None:
                return None
            event = temp_event
        return event

    return run_before_send


class SentryInstrument(Instrument[SentryConfig]):
    instrument_name = "Sentry"
    ready_condition = "Provide sentry_dsn"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.sentry_dsn)

    def bootstrap(self) -> None:
        baggage_integration: typing.Final = (
            SentryOpentelemetryBaggageIntegration(
                self.instrument_config.sentry_opentelemetry_baggage_keys,
                self.instrument_config.sentry_opentelemetry_baggage_url_templates,
            )
            if (
                self.instrument_config.sentry_opentelemetry_baggage_keys
                or self.instrument_config.sentry_opentelemetry_baggage_url_templates
            )
            else None
        )
        sentry_sdk.init(
            dsn=self.instrument_config.sentry_dsn,
            sample_rate=self.instrument_config.sentry_sample_rate,
            traces_sample_rate=self.instrument_config.sentry_traces_sample_rate,
            environment=self.instrument_config.service_environment,
            max_breadcrumbs=self.instrument_config.sentry_max_breadcrumbs,
            max_value_length=self.instrument_config.sentry_max_value_length,
            attach_stacktrace=self.instrument_config.sentry_attach_stacktrace,
            before_send=wrap_before_send_callbacks(
                enrich_sentry_event_from_structlog_log,
                functools.partial(
                    add_trace_url_to_event, self.instrument_config.sentry_opentelemetry_trace_url_template
                )
                if self.instrument_config.sentry_opentelemetry_trace_url_template
                else None,
                functools.partial(
                    enrich_sentry_event_from_opentelemetry_baggage,
                    self.instrument_config.sentry_opentelemetry_baggage_keys,
                    self.instrument_config.sentry_opentelemetry_baggage_url_templates,
                )
                if (
                    self.instrument_config.sentry_opentelemetry_baggage_keys
                    or self.instrument_config.sentry_opentelemetry_baggage_url_templates
                )
                else None,
                self.instrument_config.sentry_before_send,
            ),
            integrations=[
                *self.instrument_config.sentry_integrations,
                *([baggage_integration] if baggage_integration else []),
            ],
            **self.instrument_config.sentry_additional_params,
        )
        if self.instrument_config.sentry_tags:
            # for sentry<2.1.0
            with contextlib.suppress(AttributeError):
                sentry_sdk.set_tags(self.instrument_config.sentry_tags)

    @classmethod
    def get_config_type(cls) -> type[SentryConfig]:
        return SentryConfig
