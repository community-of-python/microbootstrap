from __future__ import annotations

import structlog

from microbootstrap.base.logging import config as logging_configs


def test_helpers__logging_configs__single_struct() -> None:
    message_to_log = "log message"

    logger_factory = structlog.testing.CapturingLoggerFactory()
    logging_config = logging_configs.SingleStructLoggingConfig(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=logger_factory,
    )

    logging_config.configure()("testing").info(message_to_log)

    calls: list[structlog.testing.CapturedCall] = logger_factory.logger.calls
    assert len(calls) == 1
    assert calls[0].method_name == "info"
