from __future__ import annotations
import re
import typing

import pydantic

from microbootstrap.helpers import is_valid_path
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument
from microbootstrap.instruments.openapi_security_schemes import OpenApiSecurityScheme  # noqa: TC001
from microbootstrap.instruments.openapi_version_docs import (
    OpenApiVersionDocsConfig,  # noqa: TC001 - Pydantic resolves it at runtime.
)


SECURITY_SCHEME_NAME_PATTERN: typing.Final = re.compile(r"^[a-zA-Z0-9._-]+$")


class SwaggerConfig(BaseInstrumentConfig):
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"

    service_static_path: str = "/static"
    swagger_path: str = "/docs"
    swagger_offline_docs: bool = False
    swagger_extra_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
    security_schemes: dict[str, OpenApiSecurityScheme] = pydantic.Field(default_factory=dict)
    openapi_version_docs: OpenApiVersionDocsConfig | None = None

    @pydantic.field_validator("security_schemes")
    @classmethod
    def validate_security_scheme_names(
        cls,
        security_schemes: dict[str, OpenApiSecurityScheme],
    ) -> dict[str, OpenApiSecurityScheme]:
        for scheme_name in security_schemes:
            if SECURITY_SCHEME_NAME_PATTERN.fullmatch(scheme_name) is None:
                message = "OpenAPI security scheme names must match ^[a-zA-Z0-9._-]+$."
                raise ValueError(message)
        return security_schemes


class SwaggerInstrument(Instrument[SwaggerConfig]):
    instrument_name = "Swagger"
    ready_condition = "Provide valid swagger_path"

    def is_ready(self) -> bool:
        return bool(self.instrument_config.swagger_path) and is_valid_path(self.instrument_config.swagger_path)

    @classmethod
    def get_config_type(cls) -> type[SwaggerConfig]:
        return SwaggerConfig
