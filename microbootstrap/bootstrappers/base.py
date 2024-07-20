from __future__ import annotations
import abc
import dataclasses
import typing

import typing_extensions

from microbootstrap.helpers import dataclass_to_dict_no_defaults, merge_dataclasses_configs, merge_dict_configs
from microbootstrap.instruments.instrument_box import InstrumentBox
from microbootstrap.settings import SettingsT


if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from microbootstrap.instruments.base import Instrument, InstrumentConfigT


ApplicationT = typing.TypeVar("ApplicationT")
DataclassT_co = typing.TypeVar("DataclassT_co", bound="DataclassInstance", covariant=True)


@dataclasses.dataclass()
class ApplicationBootstrapper(abc.ABC, typing.Generic[SettingsT, ApplicationT, DataclassT_co]):
    settings: SettingsT
    application_type: type[ApplicationT] = dataclasses.field(init=False)
    application_config: dataclasses._DataclassT = dataclasses.field(init=False)

    __instrument_box: InstrumentBox = dataclasses.field(default=InstrumentBox())

    def __post_init__(self) -> None:
        self.__instrument_box.initialize(self.settings)

    def configure_application(
        self: typing_extensions.Self,
        application_config: dataclasses._DataclassT,
    ) -> typing_extensions.Self:
        self.application_config = merge_dataclasses_configs(self.application_config, application_config)
        return self

    def configure_instrument(
        self: typing_extensions.Self,
        instrument_config: InstrumentConfigT,
    ) -> typing_extensions.Self:
        self.__instrument_box.configure_instrument(instrument_config)
        return self

    @classmethod
    def use_instrument(
        cls,
    ) -> typing.Callable[
        [type[Instrument[InstrumentConfigT]]],
        type[Instrument[InstrumentConfigT]],
    ]:
        return cls.__instrument_box.extend_instruments

    def bootstrap(self: typing_extensions.Self) -> ApplicationT:
        resulting_application_config = dataclass_to_dict_no_defaults(self.application_config)
        for instrument in self.__instrument_box.instruments:
            resulting_application_config = merge_dict_configs(
                resulting_application_config,
                instrument.bootstrap(),
            )

        application = self.application_type(
            **merge_dict_configs(resulting_application_config, self.bootstrap_before()),
        )

        for instrument in self.__instrument_box.instruments:
            application = instrument.bootstrap_after(application)
        return self.bootstrap_after(application)

    def bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        """Add some framework-related parameters to final bootstrap result before application creation."""
        return {}

    def bootstrap_after(self: typing_extensions.Self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to final bootstrap result after application creation."""
        return application

    def teardown(self: typing_extensions.Self) -> None:
        for instrument in self.__instruments:
            instrument.teardown()
