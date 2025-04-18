from __future__ import annotations

import pydantic  # noqa: TC002
import pyroscope  # type: ignore[import-untyped]

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class PyroscopeConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"

    pyroscope_endpoint: pydantic.HttpUrl | None = None
    pyroscope_sample_rate: int = 100


class PyroscopeInstrument(Instrument[PyroscopeConfig]):
    instrument_name = "Pyroscope"
    ready_condition = "Provide endpoint"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.pyroscope_endpoint)

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
