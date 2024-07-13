from __future__ import annotations
import dataclasses

import structlog

from microbootstrap.logging import base as base_logging
from microbootstrap.logging.config import SingleStructLoggingConfig
from microbootstrap.settings.litestar import LitestarBootstrapSettings


@dataclasses.dataclass()
class LitestarLoggingBootstrapper(base_logging.BaseLoggingBootstrapper[LitestarBootstrapSettings]):
    exclude_endpoints: list[str] = dataclasses.field(default_factory=list)
    config_type: type[SingleStructLoggingConfig] = dataclasses.field(default=SingleStructLoggingConfig)
    config: SingleStructLoggingConfig = dataclasses.field(init=False)

    def load_parameters(self, settings: LitestarBootstrapSettings | None = None) -> None:
        if not settings:
            return

        super().load_parameters(settings=settings)

        self.config_type = settings.logging_config_type
        self.exclude_endpoints = settings.logging_exclude_endpoints

    def initialize(self) -> None:
        super().initialize()

        self.config = self.config_type(
            processors=[
                *base_logging.DEFAULT_STRUCTLOG_PROCESSORS,
                *self.extra_processors,
                base_logging.DEFAULT_STRUCTLOG_FORMATTER_PROCESSOR,
            ],
            context_class=dict,  # type: ignore[arg-type]
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
