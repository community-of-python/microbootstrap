from __future__ import annotations
import abc
import typing

import typing_extensions

from microbootstrap.console_writer import ConsoleWriter
from microbootstrap.instruments.instrument_box import InstrumentBox
from microbootstrap.settings import SettingsT


if typing.TYPE_CHECKING:
    from microbootstrap.instruments.base import Instrument, InstrumentConfigT


class VanillaServiceSetupper(abc.ABC, typing.Generic[SettingsT]):
    console_writer: ConsoleWriter
    instrument_box: InstrumentBox

    def __init__(self, settings: SettingsT) -> None:
        self.settings = settings
        self.console_writer = ConsoleWriter(writer_enabled=settings.service_debug)

        if not hasattr(self, "instrument_box"):
            self.instrument_box = InstrumentBox()
        self.instrument_box.initialize(self.settings)

    def configure_instrument(
        self: typing_extensions.Self,
        instrument_config: InstrumentConfigT,
    ) -> typing_extensions.Self:
        self.instrument_box.configure_instrument(instrument_config)
        return self

    def configure_instruments(
        self: typing_extensions.Self,
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

    def setup(self: typing_extensions.Self) -> None:
        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                instrument.bootstrap()
            instrument.write_status(self.console_writer)

    def teardown(self: typing_extensions.Self) -> None:
        for instrument in self.instrument_box.instruments:
            instrument.teardown()

    def __enter__(self) -> None:
        self.setup()

    def __exit__(self, *args: object) -> None:
        self.teardown()
