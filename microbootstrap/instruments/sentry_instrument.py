from __future__ import annotations
import typing

import pydantic
import sentry_sdk
from sentry_sdk.integrations import Integration  # noqa: TCH002

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


if typing.TYPE_CHECKING:
    from microbootstrap.console_writer import ConsoleWriter


class SentryConfig(BaseInstrumentConfig):
    service_environment: str | None = None

    sentry_dsn: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] = pydantic.Field(default_factory=list)
    sentry_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class SentryInstrument(Instrument[SentryConfig]):
    def write_status(self, console_writer: ConsoleWriter) -> None:
        if self.is_ready():
            console_writer.write_instrument_status("Sentry", is_enabled=True)
        else:
            console_writer.write_instrument_status(
                "Sentry",
                is_enabled=False,
                disable_reason="Provide sentry_dsn",
            )

    def is_ready(self) -> bool:
        return bool(self.instrument_config.sentry_dsn)

    def teardown(self) -> None:
        return

    def bootstrap(self) -> None:
        sentry_sdk.init(
            dsn=self.instrument_config.sentry_dsn,
            sample_rate=self.instrument_config.sentry_sample_rate,
            traces_sample_rate=self.instrument_config.sentry_traces_sample_rate,
            environment=self.instrument_config.service_environment,
            max_breadcrumbs=self.instrument_config.sentry_max_breadcrumbs,
            attach_stacktrace=self.instrument_config.sentry_attach_stacktrace,
            integrations=self.instrument_config.sentry_integrations,
            **self.instrument_config.sentry_additional_params,
        )

    @classmethod
    def get_config_type(cls) -> type[SentryConfig]:
        return SentryConfig
