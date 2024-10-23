from __future__ import annotations

from health_checks.http_based import DefaultHTTPHealthCheck

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class HealthChecksConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_version: str = "1.0.0"

    health_checks_enabled: bool = True
    health_checks_path: str = "/health/"
    health_checks_include_in_schema: bool = False


class HealthChecksInstrument(Instrument[HealthChecksConfig]):
    instrument_name = "Health checks"
    ready_condition = "Set health_checks_enabled to True"

    def bootstrap(self) -> None:
        self.health_check = DefaultHTTPHealthCheck(
            service_version=self.instrument_config.service_version,
            service_name=self.instrument_config.service_name,
        )

    def is_ready(self) -> bool:
        return self.instrument_config.health_checks_enabled

    @classmethod
    def get_config_type(cls) -> type[HealthChecksConfig]:
        return HealthChecksConfig
