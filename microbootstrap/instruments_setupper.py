from __future__ import annotations
import typing

from microbootstrap.console_writer import ConsoleWriter
from microbootstrap.instruments.instrument_box import InstrumentBox
from microbootstrap.instruments.logging_instrument import LoggingInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeInstrument
from microbootstrap.instruments.sentry_instrument import SentryInstrument


if typing.TYPE_CHECKING:
    import typing_extensions

    from microbootstrap.instruments.base import Instrument, InstrumentConfigT
    from microbootstrap.settings import InstrumentsSetupperSettings


class InstrumentsSetupper:
    console_writer: ConsoleWriter
    instrument_box: InstrumentBox

    def __init__(self, settings: InstrumentsSetupperSettings) -> None:
        self.settings = settings
        self.console_writer = ConsoleWriter(writer_enabled=settings.service_debug)
        self.instrument_box.initialize(self.settings)

    def configure_instrument(self, instrument_config: InstrumentConfigT) -> typing_extensions.Self:
        self.instrument_box.configure_instrument(instrument_config)
        return self

    def configure_instruments(
        self,
        *instrument_configs: InstrumentConfigT,
    ) -> typing_extensions.Self:
        for instrument_config in instrument_configs:
            self.configure_instrument(instrument_config)
        return self

    @classmethod
    def use_instrument(
        cls,
    ) -> typing.Callable[
        [type[Instrument[InstrumentConfigT]]],
        type[Instrument[InstrumentConfigT]],
    ]:
        if not hasattr(cls, "instrument_box"):
            cls.instrument_box = InstrumentBox()
        return cls.instrument_box.extend_instruments

    def setup(self) -> None:
        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                instrument.bootstrap()
            instrument.write_status(self.console_writer)

    def teardown(self) -> None:
        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                instrument.teardown()

    def __enter__(self) -> None:
        self.setup()

    def __exit__(self, *args: object) -> None:
        self.teardown()


InstrumentsSetupper.use_instrument()(LoggingInstrument)
InstrumentsSetupper.use_instrument()(SentryInstrument)
InstrumentsSetupper.use_instrument()(OpentelemetryInstrument)
InstrumentsSetupper.use_instrument()(PyroscopeInstrument)
