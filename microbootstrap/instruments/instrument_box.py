import dataclasses
import typing

from microbootstrap import exceptions
from microbootstrap.instruments.base import Instrument, InstrumentConfigT
from microbootstrap.settings import SettingsT


@dataclasses.dataclass
class InstrumentBox:
    __instruments__: list[type[Instrument[typing.Any]]] = dataclasses.field(default_factory=list)
    __initialized_instruments__: list[Instrument[typing.Any]] = dataclasses.field(default_factory=list)

    def initialize(self, settings: SettingsT) -> None:
        settings_dump = settings.model_dump()
        self.__initialized_instruments__ = [
            instrument_type(instrument_type.get_config_type()(**settings_dump))
            for instrument_type in self.__instruments__
        ]

    def configure_instrument(
        self,
        instrument_config: InstrumentConfigT,
    ) -> None:
        for instrument in self.__initialized_instruments__:
            if isinstance(instrument_config, instrument.get_config_type()):
                instrument.configure_instrument(instrument_config)
                return

        raise exceptions.MissingInstrumentError(
            f"Instrument for config {instrument_config.__class__.__name__} is not supported yet.",
        )

    def extend_instruments(
        self,
        instrument_class: type[Instrument[InstrumentConfigT]],
    ) -> type[Instrument[InstrumentConfigT]]:
        """Extend list of instruments, excluding one whose config is already in use."""
        self.__instruments__ = list(
            filter(
                lambda instrument: instrument.get_config_type() is not instrument_class.get_config_type(),
                self.__instruments__,
            ),
        )
        self.__instruments__.append(instrument_class)
        return instrument_class

    @property
    def instruments(self) -> list[Instrument[typing.Any]]:
        return self.__initialized_instruments__
