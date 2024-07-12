from __future__ import annotations
import typing

import pydantic

from microbootstrap.instruments.base import InstrumentABC


if typing.TYPE_CHECKING:
    from sentry_sdk.integrations import Integration


class SentryConfig(pydantic.BaseModel):
    sentry_dsn: str | None = None
    environment: str | None = None
    sentry_traces_sample_rate: float | None = None
    sentry_sample_rate: float = pydantic.Field(default=1.0, le=1.0, ge=0.0)
    sentry_max_breadcrumbs: int = 15
    sentry_attach_stacktrace: bool = True
    sentry_integrations: list[Integration] | None = None
    sentry_additional_params: dict[str, typing.Any] | None = None


class SentryInstrument(InstrumentABC[SentryConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.sentry_dsn)

    def teardown(self) -> None:
        return
