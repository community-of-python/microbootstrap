from __future__ import annotations
import dataclasses
import typing

from litestar.config.app import AppConfig


if typing.TYPE_CHECKING:
    from litestar.types import OnAppInitHandler


@dataclasses.dataclass
class LitestarConfig(AppConfig):
    on_app_init: typing.Sequence[OnAppInitHandler] | None = None
