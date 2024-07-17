from __future__ import annotations
import dataclasses
import typing

import typing_extensions

from microbootstrap.helpers import dataclass_to_dict_no_defaults, merge_dataclasses_configs, merge_dict_configs
from microbootstrap.instruments import LoggingConfig, OpentelemetryConfig, SentryConfig


if typing.TYPE_CHECKING:
    from microbootstrap.instruments.base import Instrument
    from microbootstrap.settings.base import BootstrapSettings


ApplicationT = typing.TypeVar("ApplicationT")
SettingsT = typing.TypeVar("SettingsT", bound="BootstrapSettings")


@dataclasses.dataclass()
class ApplicationBootstrapper(typing.Protocol[SettingsT, ApplicationT, dataclasses._DataclassT]):
    settings: SettingsT
    application_type: type[ApplicationT] = dataclasses.field(init=False)
    application_config: dataclasses._DataclassT = dataclasses.field(init=False)

    sentry_instrument_type: type[Instrument[SentryConfig]] = dataclasses.field(init=False)
    opentelemetry_instrument_type: type[Instrument[OpentelemetryConfig]] = dataclasses.field(init=False)
    logging_instrument_type: type[Instrument[LoggingConfig]] = dataclasses.field(init=False)

    __sentry_instrument: Instrument[SentryConfig] = dataclasses.field(init=False)
    __opentelemetry_instrument: Instrument[OpentelemetryConfig] = dataclasses.field(init=False)
    __logging_instrument: Instrument[LoggingConfig] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        settings_dump = self.settings.model_dump()
        self.__sentry_instrument = self.sentry_instrument_type(SentryConfig(**settings_dump))
        self.__opentelemetry_instrument = self.opentelemetry_instrument_type(OpentelemetryConfig(**settings_dump))
        self.__logging_instrument = self.logging_instrument_type(LoggingConfig(**settings_dump))

    def configure_application(
        self: typing_extensions.Self,
        application_config: dataclasses._DataclassT,
    ) -> typing_extensions.Self:
        self.application_config = merge_dataclasses_configs(self.application_config, application_config)
        return self

    def configure_opentelemetry(
        self: typing_extensions.Self,
        opentelemetry_config: OpentelemetryConfig,
    ) -> typing_extensions.Self:
        self.__opentelemetry_instrument.configure_instrument(opentelemetry_config)
        return self

    def configure_sentry(
        self: typing_extensions.Self,
        sentry_config: SentryConfig,
    ) -> typing_extensions.Self:
        self.__sentry_instrument.configure_instrument(sentry_config)
        return self

    def configure_logging(self: typing_extensions.Self, logging_config: LoggingConfig) -> typing_extensions.Self:
        self.__logging_instrument.configure_instrument(logging_config)
        return self

    def bootstrap(self: typing_extensions.Self) -> ApplicationT:
        application_config_dict = dataclass_to_dict_no_defaults(self.application_config)
        for instrument in self.__instruments:
            application_config = merge_dict_configs(
                application_config_dict,
                instrument.bootstrap(),
            )
        return self.application_type(**application_config)

    def teardown(self: typing_extensions.Self) -> None:
        for instrument in self.__instruments:
            instrument.teardown()

    @property
    def __instruments(self) -> list[Instrument[typing.Any]]:
        return [self.__sentry_instrument, self.__opentelemetry_instrument, self.__logging_instrument]
