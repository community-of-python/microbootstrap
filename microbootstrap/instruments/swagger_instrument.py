from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument


class SwaggerConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"

    service_static_path: str = "/static"
    swagger_path: str = "/docs"
    swagger_offline_docs: bool = False
    swagger_extra_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)


class SwaggerInstrument(Instrument[SwaggerConfig]):
    instrument_name = "Swagger"
    ready_condition = "Provide valid swagger_path"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.swagger_path) and is_valid_path(self.instrument_config.swagger_path)

    @classmethod
    def get_config_type(cls) -> type[SwaggerConfig]:
        return SwaggerConfig
