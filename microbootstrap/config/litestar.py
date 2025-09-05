from __future__ import annotations
import dataclasses
import typing

from litestar.config.app import AppConfig
from litestar.logging import LoggingConfig


if typing.TYPE_CHECKING:
    from litestar.types import OnAppInitHandler


@dataclasses.dataclass
class LitestarConfig(AppConfig):
    on_app_init: typing.Sequence[OnAppInitHandler] | None = None
    logging_config: LoggingConfig = dataclasses.field(
        default_factory=lambda: LoggingConfig(
            # required for foreign logs json formatting
            configure_root_logger=False,
        )
    )
