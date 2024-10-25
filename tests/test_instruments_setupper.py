from unittest import mock

import faker
import pytest

from microbootstrap.instruments.sentry_instrument import SentryConfig
from microbootstrap.instruments_setupper import InstrumentsSetupper
from microbootstrap.settings import InstrumentsSetupperSettings


def test_instruments_setupper_initializes_instruments() -> None:
    settings = InstrumentsSetupperSettings()
    assert InstrumentsSetupper(settings).instrument_box.instruments


def test_instruments_setupper_applies_new_config(monkeypatch: pytest.MonkeyPatch, faker: faker.Faker) -> None:
    monkeypatch.setattr("sentry_sdk.init", sentry_sdk_init_mock := mock.Mock())
    sentry_dsn = faker.pystr()
    setupper = InstrumentsSetupper(InstrumentsSetupperSettings()).configure_instruments(
        SentryConfig(sentry_dsn=sentry_dsn)
    )

    with setupper:
        pass

    assert len(sentry_sdk_init_mock.mock_calls) == 1
    assert sentry_sdk_init_mock.mock_calls[0].kwargs.get("dsn") == sentry_dsn


def test_instruments_setupper_causes_instruments_lifespan() -> None:
    setupper = InstrumentsSetupper(InstrumentsSetupperSettings())
    instruments_count = len(setupper.instrument_box.instruments)
    setupper.instrument_box.__initialized_instruments__ = [mock.Mock() for _ in range(instruments_count)]

    with setupper:
        pass

    all_mock_calls = [one_mocked_instrument.mock_calls for one_mocked_instrument in setupper.instrument_box.instruments]
    expected_successful_instrument_calls = [
        mock.call.is_ready(),
        mock.call.bootstrap(),
        mock.call.write_status(setupper.console_writer),
        mock.call.teardown(),
    ]
    assert all_mock_calls == [expected_successful_instrument_calls] * instruments_count
