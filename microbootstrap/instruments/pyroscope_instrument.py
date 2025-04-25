from __future__ import annotations
import typing

import pydantic

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


try:
    import pyroscope  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pyroscope = None  # Not supported on Windows


class PyroscopeConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    opentelemetry_service_name: str | None = None
    opentelemetry_namespace: str | None = None

    pyroscope_endpoint: pydantic.HttpUrl | None = None
    pyroscope_sample_rate: int = 100
    pyroscope_auth_token: str | None = None
    pyroscope_tags: dict[str, str] = pydantic.Field(default_factory=dict)
    pyroscope_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class PyroscopeInstrument(Instrument[PyroscopeConfig]):
    instrument_name = "Pyroscope"
    ready_condition = "Provide pyroscope_endpoint"

    def is_ready(self) -> bool:
        return all([self.instrument_config.pyroscope_endpoint, pyroscope])

    def teardown(self) -> None:
        pyroscope.shutdown()

    def bootstrap(self) -> None:
        pyroscope.configure(
            application_name=self.instrument_config.opentelemetry_service_name or self.instrument_config.service_name,
            server_address=str(self.instrument_config.pyroscope_endpoint),
            auth_token=self.instrument_config.pyroscope_auth_token or "",
            sample_rate=self.instrument_config.pyroscope_sample_rate,
            tags=(
                {"service_namespace": self.instrument_config.opentelemetry_namespace}
                if self.instrument_config.opentelemetry_namespace
                else {}
            )
            | self.instrument_config.pyroscope_tags,
            **self.instrument_config.pyroscope_additional_params,
        )

    @classmethod
    def get_config_type(cls) -> type[PyroscopeConfig]:
        return PyroscopeConfig
