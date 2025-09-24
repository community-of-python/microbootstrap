from __future__ import annotations
import contextlib
import functools
import typing

import orjson
import pydantic
import sentry_sdk
from sentry_sdk import _types as sentry_types
from sentry_sdk.integrations import Integration  # noqa: TC002

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


def add_trace_url_to_event(
    trace_link_template: str, event: sentry_types.Event, _hint: sentry_types.Hint
) -> sentry_types.Event:
    if trace_link_template and (trace_id := event.get("extra", {}).get(SENTRY_EXTRA_OTEL_TRACE_ID_KEY)):
        event["extra"][SENTRY_EXTRA_OTEL_TRACE_URL_KEY] = trace_link_template.replace("{trace_id}", str(trace_id))
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
                self.instrument_config.sentry_before_send,
            ),
            integrations=self.instrument_config.sentry_integrations,
            **self.instrument_config.sentry_additional_params,
        )
        if self.instrument_config.sentry_tags:
            # for sentry<2.1.0
            with contextlib.suppress(AttributeError):
                sentry_sdk.set_tags(self.instrument_config.sentry_tags)

    @classmethod
    def get_config_type(cls) -> type[SentryConfig]:
        return SentryConfig
