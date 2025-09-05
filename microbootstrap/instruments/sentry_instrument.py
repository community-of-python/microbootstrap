from __future__ import annotations
import contextlib
import typing

import orjson
import pydantic
import sentry_sdk
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


IGNORED_STRUCTLOG_ATTRIBUTES: typing.Final = frozenset({"event", "level", "logger", "tracing", "timestamp"})


def before_send(event, _):
    print("EHRJEHRJKEH")
    print(logentry := event.get("logentry"), logentry.get("contexts"), logentry.get("formatted"))
    if (
        (logentry := event.get("logentry"))
        and (formatted_log := logentry.get("formatted"))
        and formatted_log.startswith("{")
        and (event_extra := event.get("contexts"))
    ):
        try:
            loaded_formatted_log = orjson.loads(formatted_log)
        except orjson.JSONDecodeError:
            print("NOT LOADED")
            return event

        if not isinstance(loaded_formatted_log, dict):
            print("NOT DICT")
            return event

        if event_name := loaded_formatted_log.get("event"):
            event["logentry"]["formatted"] = event_name

        additional_extra = loaded_formatted_log
        for one_attr in IGNORED_STRUCTLOG_ATTRIBUTES:
            additional_extra.pop(one_attr, None)
        print("add", additional_extra)
        if additional_extra:
            event["contexts"]["structlog"] = additional_extra
        print("add2", event["contexts"])

        print("JFDSKLJ")
    return event


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
            before_send=before_send,
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
