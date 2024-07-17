from __future__ import annotations
import dataclasses
import typing

import typing_extensions

from microbootstrap.helpers import dataclass_to_dict_no_defaults, merge_dataclasses_configs, merge_dict_configs
from microbootstrap.instruments import LoggingConfig, OpentelemetryConfig, PrometheusConfig, SentryConfig
from microbootstrap.instruments.base import Instrument


if typing.TYPE_CHECKING:
    from _typeshed import DataclassInstance

    from microbootstrap.settings import BootstrapSettings


ApplicationT = typing.TypeVar("ApplicationT")
SettingsT = typing.TypeVar("SettingsT", bound="BootstrapSettings")
DataclassT_co = typing.TypeVar("DataclassT_co", bound="DataclassInstance", covariant=True)


@dataclasses.dataclass()
@typing.runtime_checkable
class ApplicationBootstrapper(typing.Protocol[SettingsT, ApplicationT, DataclassT_co]):
    settings: SettingsT
    application_type: type[ApplicationT] = dataclasses.field(init=False)
    application_config: dataclasses._DataclassT = dataclasses.field(init=False)

    sentry_instrument_type: type[Instrument[SentryConfig]] = dataclasses.field(init=False)
    opentelemetry_instrument_type: type[Instrument[OpentelemetryConfig]] = dataclasses.field(init=False)
    logging_instrument_type: type[Instrument[LoggingConfig]] = dataclasses.field(init=False)
    prometheus_instrument_type: type[Instrument[PrometheusConfig]] = dataclasses.field(init=False)

    __sentry_instrument: Instrument[SentryConfig] = dataclasses.field(init=False)
    __opentelemetry_instrument: Instrument[OpentelemetryConfig] = dataclasses.field(init=False)
    __logging_instrument: Instrument[LoggingConfig] = dataclasses.field(init=False)
    __prometheus_instrument: Instrument[PrometheusConfig] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        settings_dump = self.settings.model_dump()
        self.__sentry_instrument = self.sentry_instrument_type(SentryConfig(**settings_dump))
        self.__opentelemetry_instrument = self.opentelemetry_instrument_type(OpentelemetryConfig(**settings_dump))
        self.__logging_instrument = self.logging_instrument_type(LoggingConfig(**settings_dump))
        self.__prometheus_instrument = self.prometheus_instrument_type(PrometheusConfig(**settings_dump))

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

    def configure_prometheus(
        self: typing_extensions.Self,
        prometheus_config: PrometheusConfig,
    ) -> typing_extensions.Self:
        self.__prometheus_instrument.configure_instrument(prometheus_config)
        return self

    def configure_logging(self: typing_extensions.Self, logging_config: LoggingConfig) -> typing_extensions.Self:
        self.__logging_instrument.configure_instrument(logging_config)
        return self

    def bootstrap(self: typing_extensions.Self) -> ApplicationT:
        resulting_application_config = dataclass_to_dict_no_defaults(self.application_config)
        for instrument in self.__instruments:
            resulting_application_config = merge_dict_configs(
                resulting_application_config,
                instrument.bootstrap(),
            )
        application = self.application_type(
            **merge_dict_configs(resulting_application_config, self.__extra_bootstrap_before()),
        )
        return self.__extra_bootstrap_after(application)

    def __extra_bootstrap_before(self: typing_extensions.Self) -> dict[str, typing.Any]:
        """Add some framework-related parameters to final bootstrap result before application creation."""
        return {}

    def __extra_bootstrap_after(self: typing_extensions.Self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to final bootstrap result after application creation."""
        return application

    def teardown(self: typing_extensions.Self) -> None:
        for instrument in self.__instruments:
            instrument.teardown()

    @property
    def __instruments(self) -> list[Instrument[typing.Any]]:
        return [
            bootsrap_instument
            for bootsrap_instument in vars(self).values()
            if isinstance(bootsrap_instument, Instrument)
        ]
