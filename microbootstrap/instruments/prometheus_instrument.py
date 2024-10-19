from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


PrometheusConfigT = typing.TypeVar("PrometheusConfigT", bound="BasePrometheusConfig")


class BasePrometheusConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"

    prometheus_metrics_path: str = "/metrics"
    prometheus_metrics_include_in_schema: bool = False


class LitestarPrometheusConfig(BasePrometheusConfig):
    prometheus_additional_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class FastApiPrometheusConfig(BasePrometheusConfig):
    prometheus_instrumentator_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    prometheus_instrument_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    prometheus_expose_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class PrometheusInstrument(Instrument[PrometheusConfigT]):
    instrument_name = "Prometheus"
    ready_condition = "Provide metrics_path for metrics exposure"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.prometheus_metrics_path) and is_valid_path(
            self.instrument_config.prometheus_metrics_path,
        )

    @classmethod
    def get_config_type(cls) -> type[PrometheusConfigT]:
        return BasePrometheusConfig  # type: ignore[return-value]
