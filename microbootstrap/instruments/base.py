from __future__ import annotations
import abc
import dataclasses
import typing

import pydantic

from microbootstrap.helpers import merge_pydantic_configs


if typing.TYPE_CHECKING:
    from microbootstrap.console_writer import ConsoleWriter


InstrumentConfigT = typing.TypeVar("InstrumentConfigT", bound="BaseInstrumentConfig")
ApplicationT = typing.TypeVar("ApplicationT", bound=typing.Any)


class BaseInstrumentConfig(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


@dataclasses.dataclass
class Instrument(abc.ABC, typing.Generic[InstrumentConfigT]):
    instrument_config: InstrumentConfigT
    instrument_name: typing.ClassVar[str]
    ready_condition: typing.ClassVar[str]

    def configure_instrument(
        self,
        incoming_config: InstrumentConfigT,
    ) -> None:
        self.instrument_config = merge_pydantic_configs(self.instrument_config, incoming_config)

    def write_status(self, console_writer: ConsoleWriter) -> None:
        console_writer.write_instrument_status(
            self.instrument_name,
            is_enabled=self.is_ready(),
            disable_reason=None if self.is_ready() else self.ready_condition,
        )

    @abc.abstractmethod
    def is_ready(self) -> bool: ...

    @classmethod
    @abc.abstractmethod
    def get_config_type(cls) -> type[InstrumentConfigT]:
        raise NotImplementedError

    def bootstrap(self) -> None:
        return None

    def teardown(self) -> None:
        return None

    def bootstrap_before(self) -> dict[str, typing.Any]:
        """Add some framework-related parameters to final bootstrap result before application creation."""
        return {}

    def bootstrap_after(self, application: ApplicationT) -> ApplicationT:
        """Add some framework-related parameters to final bootstrap result after application creation."""
        return application
