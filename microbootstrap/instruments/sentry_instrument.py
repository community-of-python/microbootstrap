from __future__ import annotations
import typing

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
            integrations=self.instrument_config.sentry_integrations,
            **self.instrument_config.sentry_additional_params,
        )

    @classmethod
    def get_config_type(cls) -> type[SentryConfig]:
        return SentryConfig
