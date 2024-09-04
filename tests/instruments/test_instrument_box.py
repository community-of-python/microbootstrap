import typing

import pytest

from microbootstrap.exceptions import MissingInstrumentError
from microbootstrap.instruments.base import Instrument
from microbootstrap.instruments.instrument_box import InstrumentBox
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.prometheus_instrument import BasePrometheusConfig, PrometheusInstrument
from microbootstrap.instruments.sentry_instrument import SentryConfig, SentryInstrument
from microbootstrap.settings import BaseServiceSettings


@pytest.mark.parametrize(
    "instruments_in_box",
    [
        [SentryInstrument, LoggingInstrument],
        [OpentelemetryInstrument],
        [PrometheusInstrument, LoggingInstrument],
        [PrometheusInstrument, LoggingInstrument, OpentelemetryInstrument, SentryInstrument],
    ],
)
def test_instrument_box_initialize(
    instruments_in_box: list[type[Instrument[typing.Any]]],
    base_settings: BaseServiceSettings,
) -> None:
    instrument_box: typing.Final = InstrumentBox()
    instrument_box.__instruments__ = instruments_in_box
    instrument_box.initialize(base_settings)

    assert len(instrument_box.instruments) == len(instruments_in_box)
    for initialized_instrument in instrument_box.instruments:
        assert isinstance(initialized_instrument, tuple(instruments_in_box))


def test_instrument_box_configure_instrument(
    base_settings: BaseServiceSettings,
) -> None:
    instrument_box: typing.Final = InstrumentBox()
    instrument_box.__instruments__ = [SentryInstrument]
    instrument_box.initialize(base_settings)
    test_dsn: typing.Final = "my-test-dsn"
    instrument_box.configure_instrument(SentryConfig(sentry_dsn=test_dsn))

    assert len(instrument_box.instruments) == 1
    assert isinstance(instrument_box.instruments[0].instrument_config, SentryConfig)
    assert instrument_box.instruments[0].instrument_config.sentry_dsn == test_dsn


def test_instrument_box_configure_instrument_error(
    base_settings: BaseServiceSettings,
) -> None:
    instrument_box: typing.Final = InstrumentBox()
    instrument_box.__instruments__ = [SentryInstrument]
    instrument_box.initialize(base_settings)

    with pytest.raises(MissingInstrumentError):
        instrument_box.configure_instrument(BasePrometheusConfig())


def test_instrument_box_extend_instruments() -> None:
    class TestSentryInstrument(SentryInstrument):
        pass

    instrument_box: typing.Final = InstrumentBox()
    instrument_box.__instruments__ = [SentryInstrument]
    instrument_box.extend_instruments(TestSentryInstrument)
    assert len(instrument_box.__instruments__) == 1
    assert issubclass(instrument_box.__instruments__[0], TestSentryInstrument)
