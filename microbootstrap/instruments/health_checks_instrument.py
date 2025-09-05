from __future__ import annotations

import typing_extensions

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class HealthCheckTypedDict(typing_extensions.TypedDict, total=False):
    service_version: str | None
    service_name: str | None
    health_status: bool


class HealthChecksConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_version: str = "1.0.0"

    health_checks_enabled: bool = True
    health_checks_path: str = "/health/"
    health_checks_include_in_schema: bool = False


class HealthChecksInstrument(Instrument[HealthChecksConfig]):
    instrument_name = "Health checks"
    ready_condition = "Set health_checks_enabled to True"

    def render_health_check_data(self) -> HealthCheckTypedDict:
        return {
            "service_version": self.instrument_config.service_version,
            "service_name": self.instrument_config.service_name,
            "health_status": True,
        }

    def is_ready(self) -> bool:
        return self.instrument_config.health_checks_enabled

    @classmethod
    def get_config_type(cls) -> type[HealthChecksConfig]:
        return HealthChecksConfig
