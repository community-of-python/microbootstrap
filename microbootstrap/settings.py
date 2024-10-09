from __future__ import annotations
import os
import typing

import pydantic_settings

from microbootstrap import (
    CorsConfig,
    FastApiPrometheusConfig,
    LitestarPrometheusConfig,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    SwaggerConfig,
)


SettingsT = typing.TypeVar("SettingsT", bound="BaseServiceSettings")
ENVIRONMENT_PREFIX: typing.Final = "ENVIRONMENT_PREFIX"


# TODO: add offline docs and cors support  # noqa: TD002
class BaseServiceSettings(
    pydantic_settings.BaseSettings,
):
    service_debug: bool = False
    service_environment: str | None = None
    service_name: str = "micro-service"
    service_description: str = "Micro service description"
    service_version: str = "1.0.0"
    service_static_path: str = "/static"

    server_host: str = "0.0.0.0"  # noqa: S104
    server_port: int = 8000
    server_reload: bool = False
    server_workers_count: int = 1

    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_prefix=os.getenv(ENVIRONMENT_PREFIX, ""),
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


class LitestarSettings(
    BaseServiceSettings,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    LitestarPrometheusConfig,
    SwaggerConfig,
    CorsConfig,
):
    """Settings for a litestar botstrap."""


class FastApiSettings(
    BaseServiceSettings,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    FastApiPrometheusConfig,
    SwaggerConfig,
    CorsConfig,
):
    """Settings for a fastapi botstrap."""
