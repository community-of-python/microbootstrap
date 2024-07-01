from __future__ import annotations
import dataclasses
import typing


if typing.TYPE_CHECKING:
    from microbootstrap.settings.base import BootstrapSettings


Application_contra = typing.TypeVar("Application_contra", contravariant=True)
Settings_contra = typing.TypeVar("Settings_contra", bound="BootstrapSettings", contravariant=True)
ReturnType_co = typing.TypeVar("ReturnType_co", covariant=True)


@dataclasses.dataclass()
class BootstrapServicesBootstrapper(typing.Protocol[Settings_contra]):
    def load_parameters(self, settings: Settings_contra | None = None) -> None: ...
    def initialize(self) -> None: ...
    def teardown(self) -> None: ...
    @property
    def ready(self) -> bool: ...


@dataclasses.dataclass()
class BootstrapWebFrameworkBootstrapper(typing.Protocol[Application_contra, Settings_contra, ReturnType_co]):
    def load_parameters(self, app: Application_contra, settings: Settings_contra | None = None) -> None: ...
    def initialize(self) -> ReturnType_co: ...
    def teardown(self) -> None: ...
