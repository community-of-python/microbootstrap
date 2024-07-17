from __future__ import annotations
import typing

import pydantic
import pydantic_settings

from microbootstrap.instruments import LoggingConfig, OpentelemetryConfig, SentryConfig


class BootstrapSettings(pydantic_settings.BaseSettings, LoggingConfig, OpentelemetryConfig, SentryConfig):
    debug: bool = False
    app_environment: str | None = None
    service_name: str = pydantic.Field(default="micro-service")
    service_version: str = pydantic.Field(default="1.0.0")
    container_name: str | None = pydantic.Field(default=None)

    prometheus_endpoint: str | None = None
    prometheus_basic_auth: dict[str, str | int | bytes] = {}
    prometheus_headers: dict[str, typing.Any] = {}
    prometheus_timeout: int = 30
    prometheus_proxies: dict[str, str] = {}
    prometheus_tls_config: dict[str, typing.Any] = {}

    server_host: str = "0.0.0.0"  # noqa: S104
    server_port: int = 8000
    server_reload: bool = True
    server_workers_count: int = 1

    class Config:
        allow_population_by_field_name = True
