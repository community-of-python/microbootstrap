from __future__ import annotations
import abc
import dataclasses
import typing

from microbootstrap.helpers import merge_dataclasses_configs, merge_dict_configs
from microbootstrap.instruments import OpentelemetryConfig, SentryConfig


if typing.TYPE_CHECKING:
    from microbootstrap.instruments import Instrument
    from microbootstrap.settings.base import BootstrapSettings


ApplicationT = typing.TypeVar("ApplicationT")
SettingsT = typing.TypeVar("SettingsT", bound="BootstrapSettings")
SelfT = typing.TypeVar("SelfT", bound="ApplicationBootstrapper[typing.Any, typing.Any, typing.Any]")


@dataclasses.dataclass()
class ApplicationBootstrapper(typing.Protocol[SettingsT, ApplicationT, dataclasses._DataclassT]):
    settings: SettingsT
    application_type: type[ApplicationT] = dataclasses.field(init=False)
    application_config: dataclasses._DataclassT = dataclasses.field(init=False)

    sentry_instrument_type: type[Instrument[SentryConfig]] = dataclasses.field(init=False)
    sentry_instrument: Instrument[SentryConfig] = dataclasses.field(init=False)
    opentelemetry_instrument_type: type[Instrument[OpentelemetryConfig]] = dataclasses.field(init=False)
    opentelemetry_instrument: Instrument[OpentelemetryConfig] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        settings_dump = self.settings.model_dump()
        self.sentry_instrument = self.sentry_instrument_type(SentryConfig(**settings_dump))
        self.opentelemetry_instrument = self.opentelemetry_instrument_type(OpentelemetryConfig(**settings_dump))

    @abc.abstractmethod
    def configure_application(self: SelfT, application_config: dataclasses._DataclassT) -> SelfT:
        self.application_config = merge_dataclasses_configs(self.application_config, application_config)
        return self

    @abc.abstractmethod
    def configure_opentelemetry(
        self: SelfT,
        opentelemetry_config: OpentelemetryConfig,
    ) -> SelfT:
        self.opentelemetry_instrument.configure_instrument(opentelemetry_config)
        return self

    @abc.abstractmethod
    def configure_sentry(
        self: SelfT,
        sentry_config: SentryConfig,
    ) -> SelfT:
        self.sentry_instrument.configure_instrument(sentry_config)
        return self

    @abc.abstractmethod
    def configure_logging(self: SelfT) -> SelfT:
        raise NotImplementedError

    @abc.abstractmethod
    def bootstrap(self: SelfT) -> ApplicationT:
        application_config = dataclasses.asdict(self.application_config)
        for instrument in self.__instruments:
            application_config = merge_dict_configs(application_config, instrument.bootstrap())
        return self.application_type(**application_config)

    @abc.abstractmethod
    def teardown(self: SelfT) -> None:
        for instrument in self.__instruments:
            instrument.teardown()

    @property
    def __instruments(self) -> list[Instrument[typing.Any]]:
        return [self.sentry_instrument]
