from __future__ import annotations

import pydantic

from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class CorsConfig(BaseInstrumentConfig):
    cors_allowed_origins: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_methods: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_headers: list[str] = pydantic.Field(default_factory=list)
    cors_exposed_headers: list[str] = pydantic.Field(default_factory=list)
    cors_allowed_credentials: bool = False
    cors_allowed_origin_regex: str | None = None
    cors_max_age: int = 600


class CorsInstrument(Instrument[CorsConfig]):
    instrument_name = "Cors"
    ready_condition = "Provide allowed origins or regex"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.cors_allowed_origins) or bool(
            self.instrument_config.cors_allowed_origin_regex,
        )

    @classmethod
    def get_config_type(cls) -> type[CorsConfig]:
        return CorsConfig
