from __future__ import annotations
import typing

import pydantic

from microbootstrap.settings import base as settings_base


class FastAPIBootstrapSettings(settings_base.BootstrapSettings):
    excluded_urls: str | None = None

    enable_prometheus_instrumentator: bool = True
    prometheus_instrumentator_params: dict[str, typing.Any] = pydantic.Field(default_factory=dict)
