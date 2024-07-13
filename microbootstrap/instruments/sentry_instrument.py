from __future__ import annotations
import typing

import pydantic
import sentry_sdk
from sentry_sdk.integrations import Integration  # noqa: TCH002

from microbootstrap.instruments.base import Instrument


class SentryInstrumentConfig(pydantic.BaseModel):
    sentry_dsn: str | None = None
    environment: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] | None = None
    sentry_additional_params: dict[str, typing.Any] | None = None

    class Config:
        arbitrary_types_allowed = True


class SentryInstrument(Instrument[SentryInstrumentConfig]):
    @property
    def is_ready(self) -> bool:
        return bool(self.instrument_config.sentry_dsn)

    def teardown(self) -> None:
        return

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready:
            # TODO: use some logger  # noqa: TD002
            print("Sentry is not ready for bootstrapping. Provide a sentry_dsn")  # noqa: T201
            return {}

        sentry_sdk.init(
            dsn=self.instrument_config.sentry_dsn,
            sample_rate=self.instrument_config.sentry_sample_rate,
            traces_sample_rate=self.instrument_config.sentry_traces_sample_rate,
            environment=self.instrument_config.sentry_environment,
            max_breadcrumbs=self.instrument_config.sentry_additional_paramsmax_breadcrumbs,
            attach_stacktrace=self.instrument_config.sentry_attach_stacktrace,
            integrations=self.instrument_config.sentry_integrations,
            **self.instrument_config.sentry_additional_params,
        )
        return self.successful_bootstrap_result
