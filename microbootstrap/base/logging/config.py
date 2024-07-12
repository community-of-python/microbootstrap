from __future__ import annotations
import typing

import structlog
from litestar.logging.config import StructLoggingConfig


if typing.TYPE_CHECKING:
    from litestar.types.callable_types import GetLogger


class BaseLoggingConfig(typing.Protocol):
    def configure(self) -> typing.Callable[..., typing.Any]: ...


class SingleStructLoggingConfig(StructLoggingConfig, BaseLoggingConfig):
    def configure(self) -> GetLogger:
        structlog.configure_once(
            processors=self.processors,
            context_class=self.context_class,  # type: ignore[arg-type]
            logger_factory=self.logger_factory,
            wrapper_class=self.wrapper_class,
            cache_logger_on_first_use=self.cache_logger_on_first_use,
        )
        return structlog.get_logger
