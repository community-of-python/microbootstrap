from __future__ import annotations
import typing

import pydantic

from microbootstrap.helpers.logging.config import SingleStructLoggingConfig
from microbootstrap.settings import base as settings_base


class LitestarBootstrapSettings(settings_base.BootstrapSettings):
    static_path: str | None = None

    # litestar imports types for type hints in typing.TYPE_CHECKING block, but that doesn't work with pydantic
    prometheus_controller: typing.Any = None  # type[litestar.contrib.prometheus.PrometheusController] | None
    prometheus_config: typing.Any = None  # litestar.contrib.prometheus.PrometheusConfig | None

    logging_exclude_endpoints: list[str] = pydantic.Field(default=["/metrics"])
    logging_config_type: type[SingleStructLoggingConfig] = SingleStructLoggingConfig

    opentelemetry_exclude_urls: list[str] = pydantic.Field(default=["/health"])
