from __future__ import annotations
import typing

import pydantic
import pydantic_settings

from microbootstrap.instruments import LoggingConfig, OpentelemetryConfig, PrometheusConfig, SentryConfig


SettingsT = typing.TypeVar("SettingsT", bound="BaseBootstrapSettings")


# TODO: add offline docs and cors support  # noqa: TD002
class BaseBootstrapSettings(pydantic_settings.BaseSettings):
    service_debug: bool = True
    service_environment: str | None = None
    service_name: str = pydantic.Field(default="micro-service")
    service_description: str = pydantic.Field(default="Micro service description")
    service_version: str = pydantic.Field(default="1.0.0")

    server_host: str = "0.0.0.0"  # noqa: S104
    server_port: int = 8000
    server_reload: bool = True
    server_workers_count: int = 1

    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".env",
        env_prefix="BOOTSTRAP_",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )


class LitestarSettings(
    BaseBootstrapSettings,
    LoggingConfig,
    OpentelemetryConfig,
    SentryConfig,
    PrometheusConfig,
):
    """Settings for a litestar botstrap."""