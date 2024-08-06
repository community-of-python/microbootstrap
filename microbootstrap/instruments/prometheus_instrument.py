from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class PrometheusConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"

    prometheus_metrics_path: str = "/metrics"
    prometheus_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class PrometheusInstrument(Instrument[PrometheusConfig]):
    instrument_name = "Prometheus"
    ready_condition = "Provide metrics_path for metrics exposure"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_metrics_path) and is_valid_path(
            self.instrument_config.prometheus_metrics_path,
        )

    @classmethod
    def get_config_type(cls) -> type[PrometheusConfig]:
        return PrometheusConfig
