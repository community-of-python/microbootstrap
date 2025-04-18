from __future__ import annotations

import pydantic  # noqa: TC002

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


try:
    import pyroscope  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pyroscope = None  # Not supported on Windows


class PyroscopeConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"

    pyroscope_endpoint: pydantic.HttpUrl | None = None
    pyroscope_sample_rate: int = 100


class PyroscopeInstrument(Instrument[PyroscopeConfig]):
    instrument_name = "Pyroscope"
    ready_condition = "Provide pyroscope_endpoint"

    def is_ready(self) -> bool:
        return all([self.instrument_config.pyroscope_endpoint, pyroscope])

    def teardown(self) -> None:
        pyroscope.shutdown()

    def bootstrap(self) -> None:
        pyroscope.configure(
            application_name=self.instrument_config.service_name,
            server_address=str(self.instrument_config.pyroscope_endpoint),
            sample_rate=self.instrument_config.pyroscope_sample_rate,
        )

    @classmethod
    def get_config_type(cls) -> type[PyroscopeConfig]:
        return PyroscopeConfig
