from __future__ import annotations
import abc
import typing

from microbootstrap.console_writer import ConsoleWriter
from microbootstrap.helpers import dataclass_to_dict_no_defaults, merge_dataclasses_configs, merge_dict_configs
from microbootstrap.instruments.instrument_box import InstrumentBox
from microbootstrap.settings import SettingsT


if typing.TYPE_CHECKING:
    import typing_extensions

    from microbootstrap.instruments.base import Instrument, InstrumentConfigT


class DataclassInstance(typing.Protocol):
    __dataclass_fields__: typing.ClassVar[dict[str, typing.Any]]


ApplicationT = typing.TypeVar("ApplicationT", bound=typing.Any)
DataclassT = typing.TypeVar("DataclassT", bound=DataclassInstance)


class ApplicationBootstrapper(abc.ABC, typing.Generic[SettingsT, ApplicationT, DataclassT]):
    application_type: type[ApplicationT]
    application_config: DataclassT
    console_writer: ConsoleWriter
    instrument_box: InstrumentBox

    def __init__(self, settings: SettingsT) -> None:
        self.settings = settings
        self.console_writer = ConsoleWriter(writer_enabled=settings.service_debug)

        if not hasattr(self, "instrument_box"):
            self.instrument_box = InstrumentBox()
        self.instrument_box.initialize(self.settings)

    def configure_application(
        self,
        application_config: DataclassT,
    ) -> typing_extensions.Self:
        self.application_config = merge_dataclasses_configs(self.application_config, application_config)
        return self

    def configure_instrument(
        self,
        instrument_config: InstrumentConfigT,
    ) -> typing_extensions.Self:
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

    def bootstrap(self) -> ApplicationT:
        resulting_application_config: dict[str, typing.Any] = {}
        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                instrument.bootstrap()
                resulting_application_config = merge_dict_configs(
                    resulting_application_config,
                    instrument.bootstrap_before(),
                )
            instrument.write_status(self.console_writer)

        resulting_application_config = merge_dict_configs(
            resulting_application_config,
            dataclass_to_dict_no_defaults(self.application_config),
        )
        application = self.application_type(
            **merge_dict_configs(resulting_application_config, self.bootstrap_before()),
        )

        self.bootstrap_before_instruments_after_app_created(application)

        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                application = instrument.bootstrap_after(application)

        return self.bootstrap_after(application)

    def bootstrap_before(self) -> dict[str, typing.Any]:
        """Add some framework-related parameters to final bootstrap result before application creation."""
        return {}

    def bootstrap_before_instruments_after_app_created(self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to bootstrap result after application creation, but before instruments are applied."""  # noqa: E501
        return application

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to final bootstrap result after application creation."""
        return application

    def teardown(self) -> None:
        for instrument in self.instrument_box.instruments:
            if instrument.is_ready():
                instrument.teardown()
