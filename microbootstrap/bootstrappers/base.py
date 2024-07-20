from __future__ import annotations
import abc
import dataclasses
import typing

import typing_extensions

from microbootstrap import exceptions
from microbootstrap.helpers import dataclass_to_dict_no_defaults, merge_dataclasses_configs, merge_dict_configs


if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from microbootstrap.instruments.base import Instrument, InstrumentConfigT
    from microbootstrap.settings import BootstrapSettings


ApplicationT = typing.TypeVar("ApplicationT")
SettingsT = typing.TypeVar("SettingsT", bound="BootstrapSettings")
DataclassT_co = typing.TypeVar("DataclassT_co", bound="DataclassInstance", covariant=True)


@dataclasses.dataclass()
class ApplicationBootstrapper(abc.ABC, typing.Generic[SettingsT, ApplicationT, DataclassT_co]):
    settings: SettingsT
    application_type: type[ApplicationT] = dataclasses.field(init=False)
    application_config: dataclasses._DataclassT = dataclasses.field(init=False)

    __instruments__: typing.ClassVar[list[type[Instrument[typing.Any]]]] = dataclasses.field(default=[], init=False)
    __initialized_instruments__: list[Instrument[typing.Any]] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        settings_dump = self.settings.model_dump()
        self.__initialized_instruments__ = [
            instrument_type(instrument_type.get_config_type()(**settings_dump))
            for instrument_type in self.__instruments__
        ]

    def configure_application(
        self: typing_extensions.Self,
        application_config: dataclasses._DataclassT,
    ) -> typing_extensions.Self:
        self.application_config = merge_dataclasses_configs(self.application_config, application_config)
        return self

    def __find_instrument(self, instrument_config: InstrumentConfigT) -> Instrument[InstrumentConfigT]:
        for instrument in self.__initialized_instruments__:
            if isinstance(instrument_config, instrument.get_config_type()):
                return instrument

        raise exceptions.MissingInstrumentError(
            f"Instrument for config {instrument_config.__class__.__name__} is not supported yet.",
        )

    def configure_instrument(
        self: typing_extensions.Self,
        instrument_config: InstrumentConfigT,
    ) -> typing_extensions.Self:
        self.__find_instrument(instrument_config).configure_instrument(instrument_config)
        return self

    @classmethod
    def use_instrument(cls) -> typing.Callable[[type[Instrument[typing.Any]]], type[Instrument[typing.Any]]]:
        def decorator(instrument_class: type[Instrument[typing.Any]]) -> type[Instrument[typing.Any]]:
            cls.__instruments__ = list(
                filter(
                    lambda instrument: instrument.get_config_type() is not instrument_class.get_config_type(),
                    cls.__instruments__,
                ),
            )
            cls.__instruments__.append(instrument_class)
            return instrument_class

        return decorator

    def bootstrap(self: typing_extensions.Self) -> ApplicationT:
        resulting_application_config = dataclass_to_dict_no_defaults(self.application_config)
        for instrument in self.__initialized_instruments__:
            resulting_application_config = merge_dict_configs(
                resulting_application_config,
                instrument.bootstrap(),
            )
        application = self.application_type(
            **merge_dict_configs(resulting_application_config, self.extra_bootstrap_before()),
        )
        return self.extra_bootstrap_after(application)

    def extra_bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        """Add some framework-related parameters to final bootstrap result before application creation."""
        return {}

    def extra_bootstrap_after(self: typing_extensions.Self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to final bootstrap result after application creation."""
        return application

    def teardown(self: typing_extensions.Self) -> None:
        for instrument in self.__instruments:
            instrument.teardown()
