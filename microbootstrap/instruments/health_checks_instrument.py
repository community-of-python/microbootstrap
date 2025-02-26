from __future__ import annotations
import contextlib
import typing

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


if typing.TYPE_CHECKING:
    from health_checks.base import HealthCheck


with contextlib.suppress(ImportError):
    from health_checks.http_based import DefaultHTTPHealthCheck


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
        self.health_check: HealthCheck = DefaultHTTPHealthCheck(
            service_version=self.instrument_config.service_version,
            service_name=self.instrument_config.service_name,
        )

    def is_ready(self) -> bool:
        return self.instrument_config.health_checks_enabled

    @classmethod
    def get_config_type(cls) -> type[HealthChecksConfig]:
        return HealthChecksConfig
