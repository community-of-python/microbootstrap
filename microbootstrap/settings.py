from __future__ import annotations
import os
import typing

import pydantic
import pydantic_settings

from microbootstrap import (
    CorsConfig,
    FastApiPrometheusConfig,
    FastStreamOpentelemetryConfig,
    FastStreamPrometheusConfig,
    HealthChecksConfig,
    LitestarPrometheusConfig,
    LoggingConfig,
    OpentelemetryConfig,
    PyroscopeConfig,
    SentryConfig,
    SwaggerConfig,
)


SettingsT = typing.TypeVar("SettingsT", bound="BaseServiceSettings")
ENV_PREFIX_VAR_NAME: typing.Final = "ENVIRONMENT_PREFIX"
ENV_PREFIX: typing.Final = os.getenv(ENV_PREFIX_VAR_NAME, "")


# TODO: add offline docs and cors support  # noqa: TD002
class BaseServiceSettings(
    pydantic_settings.BaseSettings,
):
    service_debug: bool = True
    service_environment: str | None = None
    service_name: str = pydantic.Field(
        "micro-service",
        validation_alias=pydantic.AliasChoices("SERVICE_NAME", f"{ENV_PREFIX}SERVICE_NAME"),
    )
    service_description: str = "Micro service description"
    service_version: str = pydantic.Field(
        "1.0.0",
        validation_alias=pydantic.AliasChoices("CI_COMMIT_TAG", f"{ENV_PREFIX}SERVICE_VERSION"),
    )

    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_prefix=ENV_PREFIX,
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="allow",
    )


class ServerConfig(pydantic.BaseModel):
    server_host: str = "0.0.0.0"  # noqa: S104
    server_port: int = 8000
    server_reload: bool = True
    server_workers_count: int = 1


class LitestarSettings(  # type: ignore[misc]
    BaseServiceSettings,
    ServerConfig,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    LitestarPrometheusConfig,
    SwaggerConfig,
    CorsConfig,
    HealthChecksConfig,
    PyroscopeConfig,
):
    """Settings for a litestar botstrap."""


class FastApiSettings(  # type: ignore[misc]
    BaseServiceSettings,
    ServerConfig,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    FastApiPrometheusConfig,
    SwaggerConfig,
    CorsConfig,
    HealthChecksConfig,
    PyroscopeConfig,
):
    """Settings for a fastapi botstrap."""


class FastStreamSettings(  # type: ignore[misc]
    BaseServiceSettings,
    ServerConfig,
    LoggingConfig,
    FastStreamOpentelemetryConfig,
    SentryConfig,
    FastStreamPrometheusConfig,
    HealthChecksConfig,
    PyroscopeConfig,
):
    """Settings for a faststream bootstrap."""

    asyncapi_path: str | None = "/asyncapi"


class InstrumentsSetupperSettings(  # type: ignore[misc]
    BaseServiceSettings,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    PyroscopeConfig,
):
    """Settings for a vanilla service."""
