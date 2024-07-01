from __future__ import annotations
import typing
import warnings

import pytest
import structlog
from structlog.testing import LogCapture

from microbootstrap.helpers.logging import base as logging_base
from microbootstrap.helpers.logging import litestar as logging_litestar
from tests import settings_for_test


if typing.TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from microbootstrap.settings.base import BootstrapSettings


@pytest.mark.parametrize(
    "logging_bootstrapper_type",
    [
        logging_litestar.LitestarLoggingBootstrapper,
        logging_base.LoggingBootstrapper,
    ],
)
def test_helpers__logging(logging_bootstrapper_type: type[logging_base.BaseLoggingBootstrapper[typing.Any]]) -> None:
    message_to_log = "log message"
    log_output: typing.Final[LogCapture] = LogCapture()

    logging_bootstrapper = logging_bootstrapper_type(
        is_debug=False,
        extra_processors=[
            log_output,
        ],
    )
    if isinstance(logging_bootstrapper, logging_litestar.LitestarLoggingBootstrapper):
        logging_bootstrapper.exclude_endpoints = ["/health"]

    logging_bootstrapper.initialize()

    get_logger = structlog.get_logger
    if isinstance(logging_bootstrapper, logging_litestar.LitestarLoggingBootstrapper):
        get_logger = logging_bootstrapper.config.configure()

    get_logger("testing").info(message_to_log)
    test_log_entry: typing.Final = log_output.entries[0]
    assert "tracing" in test_log_entry

    for opentelemetry_id in ("span_id", "trace_id"):
        assert opentelemetry_id in test_log_entry["tracing"]

    logging_bootstrapper.teardown()


@pytest.mark.parametrize(
    "logging_bootstrapper_type",
    [
        logging_litestar.LitestarLoggingBootstrapper,
        logging_base.LoggingBootstrapper,
    ],
)
def test_helpers__logging__load(
    logging_bootstrapper_type: type[logging_base.BaseLoggingBootstrapper[typing.Any]],
    mocker: MockerFixture,
) -> None:
    message_to_log = "log message"
    log_output: typing.Final[LogCapture] = LogCapture()

    logging_bootstrapper = logging_bootstrapper_type(is_debug=True)
    bootstrap_settings_type: type[BootstrapSettings] = settings_for_test.TestBootstrapSettings
    if isinstance(logging_bootstrapper, logging_litestar.LitestarLoggingBootstrapper):
        logging_bootstrapper.exclude_endpoints = ["/health"]
        bootstrap_settings_type = settings_for_test.TestLitestarBootstrapSettings

    env_vars = {
        "debug": False,
        "logging_buffer_capacity": 1024 * 100,
        "logging_extra_processors": [
            log_output,
        ],
    }
    mocker.patch.object(bootstrap_settings_type, "_settings_build_values", return_value=env_vars)

    bootstrap_settings = bootstrap_settings_type()
    logging_bootstrapper.load_parameters(settings=bootstrap_settings)

    assert not logging_bootstrapper.is_debug
    assert logging_bootstrapper.buffer_capacity == 1024 * 100

    logging_bootstrapper.initialize()

    get_logger = structlog.get_logger
    if isinstance(logging_bootstrapper, logging_litestar.LitestarLoggingBootstrapper):
        get_logger = logging_bootstrapper.config.configure()

    get_logger("testing").info(message_to_log)
    test_log_entry: typing.Final = log_output.entries[0]
    assert "tracing" in test_log_entry

    for opentelemetry_id in ("span_id", "trace_id"):
        assert opentelemetry_id in test_log_entry["tracing"]

    logging_bootstrapper.teardown()


@pytest.mark.parametrize(
    "logging_bootstrapper_type",
    [
        logging_litestar.LitestarLoggingBootstrapper,
        logging_base.LoggingBootstrapper,
    ],
)
def test_helpers__logging__load__without_settings(
    logging_bootstrapper_type: type[logging_base.BaseLoggingBootstrapper[typing.Any]],
) -> None:
    logging_bootstrapper = logging_bootstrapper_type(
        is_debug=False,
    )
    logging_bootstrapper.load_parameters()

    assert logging_bootstrapper


def test_helpers__logging__zero_buffer_capacity() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        logging_bootstrapper = logging_base.LoggingBootstrapper[typing.Any](is_debug=False)

        logging_bootstrapper.initialize()

        assert len(w) == 1
        assert issubclass(w[-1].category, UserWarning)
        assert "Your buffer capacity is 0 in non-debug mode." in str(w[-1].message)

        logging_bootstrapper.teardown()


def test_helpers__logging__zero_buffer_capacity__debug() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        logging_bootstrapper = logging_base.LoggingBootstrapper[typing.Any](is_debug=True)

        logging_bootstrapper.initialize()

        assert not w

        logging_bootstrapper.teardown()
