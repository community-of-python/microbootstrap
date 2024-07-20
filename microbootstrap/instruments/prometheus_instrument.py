from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class PrometheusConfig(BaseInstrumentConfig):
    service_name: str | None = None

    prometheus_metrics_path: str = pydantic.Field(default="/metrics")
    prometheus_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class PrometheusInstrument(Instrument[PrometheusConfig]):
    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_metrics_path) and is_valid_path(
            self.instrument_config.prometheus_metrics_path,
        )

    def teardown(self) -> None:
        return

    def bootstrap(self) -> dict[str, typing.Any]:
        if not self.is_ready():
            # TODO: use some logger  # noqa: TD002
            print("Prometheus is not ready for bootstrapping. Provide a valid prometheus_metrics_path")  # noqa: T201
            return {}

        return self.bootstrap_before()

    @classmethod
    def get_config_type(cls) -> type[PrometheusConfig]:
        return PrometheusConfig
