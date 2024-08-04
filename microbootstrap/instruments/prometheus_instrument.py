from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


if typing.TYPE_CHECKING:
    from microbootstrap.console_writer import ConsoleWriter


class PrometheusConfig(BaseInstrumentConfig):
    service_name: str = pydantic.Field(default="micro-service")

    prometheus_metrics_path: str = pydantic.Field(default="/metrics")
    prometheus_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class PrometheusInstrument(Instrument[PrometheusConfig]):
    def write_status(self, console_writer: ConsoleWriter) -> None:
        if self.is_ready():
            console_writer.write_instrument_status("Prometheus", is_enabled=True)
        else:
            console_writer.write_instrument_status(
                "Prometheus",
                is_enabled=False,
                disable_reason="Provide metrics_path for metrics exposure",
            )

    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_metrics_path) and is_valid_path(
            self.instrument_config.prometheus_metrics_path,
        )

    def teardown(self) -> None:
        return

    def bootstrap(self) -> None:
        pass

    @classmethod
    def get_config_type(cls) -> type[PrometheusConfig]:
        return PrometheusConfig
