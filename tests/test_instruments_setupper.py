import typing
from unittest import mock

import faker
import pytest

from microbootstrap.instruments.sentry_instrument import SentryConfig
from microbootstrap.instruments_setupper import InstrumentsSetupper
from microbootstrap.settings import InstrumentsSetupperSettings


def test_instruments_setupper_initializes_instruments() -> None:
    settings: typing.Final = InstrumentsSetupperSettings()
    assert InstrumentsSetupper(settings).instrument_box.instruments


def test_instruments_setupper_applies_new_config(monkeypatch: pytest.MonkeyPatch, faker: faker.Faker) -> None:
    monkeypatch.setattr("sentry_sdk.init", sentry_sdk_init_mock := mock.Mock())
    sentry_dsn: typing.Final = faker.pystr()
    current_setupper: typing.Final = InstrumentsSetupper(InstrumentsSetupperSettings()).configure_instruments(
        SentryConfig(sentry_dsn=sentry_dsn)
    )

    with current_setupper:
        pass

    assert len(sentry_sdk_init_mock.mock_calls) == 1
    assert sentry_sdk_init_mock.mock_calls[0].kwargs.get("dsn") == sentry_dsn


def test_instruments_setupper_causes_instruments_lifespan() -> None:
    current_setupper: typing.Final = InstrumentsSetupper(InstrumentsSetupperSettings())
    instruments_count: typing.Final = len(current_setupper.instrument_box.instruments)
    current_setupper.instrument_box.__initialized_instruments__ = [mock.Mock() for _ in range(instruments_count)]

    with current_setupper:
        pass

    all_mock_calls: typing.Final = [
        one_mocked_instrument.mock_calls  # type: ignore[attr-defined]
        for one_mocked_instrument in current_setupper.instrument_box.instruments
    ]
    expected_successful_instrument_calls: typing.Final = [
        mock.call.is_ready(),
        mock.call.bootstrap(),
        mock.call.write_status(current_setupper.console_writer),
        mock.call.is_ready(),
        mock.call.teardown(),
    ]
    assert all_mock_calls == [expected_successful_instrument_calls] * instruments_count
