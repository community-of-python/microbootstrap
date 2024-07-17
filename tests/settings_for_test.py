from __future__ import annotations
import logging
import typing

import pydantic_settings
from litestar.contrib.prometheus import PrometheusConfig

from microbootstrap.settings import fastapi as settings_fastapi
from microbootstrap.settings import litestar as settings_litestar
from microbootstrap.settings import settings as settings_base


class TestBootstrapSettings(settings_base.BootstrapSettings):
    model_config = pydantic_settings.SettingsConfigDict(
        env_file=".test.env",
        env_prefix="BOOTSTRAP_",
        env_file_encoding="utf-8",
    )

    debug: bool = False
    service_environment: str = "test"
    service_name: str = "bootstrap"
    service_version: str = "1.0.0"
    container_name: str = "microbootstrap"

    sentry_dsn: str = "old_dsn"
    sentry_traces_sample_rate: float = 1.0

    logging_log_level: int = logging.DEBUG
    logging_buffer_capacity: int = 1024 * 100

    prometheus_endpoint: str = "prometheus.old.test"
    prometheus_timeout: int = 45

    opentelemetry_endpoint: str = "localhost.old"
    opentelemetry_add_system_metrics: bool = False


class TestFastAPIBootstrapSettings(settings_fastapi.FastAPIBootstrapSettings, TestBootstrapSettings):
    excluded_urls: str = "/metrics"

    enable_prometheus_instrumentator: bool = False

    logging_exclude_endpoints: typing.ClassVar[list[str]] = ["/metrics"]


class TestLitestarBootstrapSettings(settings_litestar.LitestarBootstrapSettings, TestBootstrapSettings):
    static_path: str = "/static"

    prometheus_config: typing.Any = PrometheusConfig()
