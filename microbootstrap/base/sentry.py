from __future__ import annotations
import dataclasses
import typing

import sentry_sdk

from microbootstrap.base.base import BootstrapServicesBootstrapper
from microbootstrap.settings.base import BootstrapSettings


if typing.TYPE_CHECKING:
    from sentry_sdk.integrations import Integration


@dataclasses.dataclass()
class SentryBootstrapper(BootstrapServicesBootstrapper[BootstrapSettings]):
    dsn: str | None = None
    sample_rate: float = dataclasses.field(default=1.0)
    traces_sample_rate: float | None = None
    environment: str | None = None
    max_breadcrumbs: int = dataclasses.field(default=15)
    attach_stacktrace: bool = dataclasses.field(default=True)
    integrations: list[Integration] = dataclasses.field(default_factory=list)
    additional_params: dict[str, typing.Any] = dataclasses.field(default_factory=dict)

    def load_parameters(self, settings: BootstrapSettings | None = None) -> None:
        if not settings:
            return

        self.dsn = settings.sentry_dsn
        self.traces_sample_rate = settings.sentry_traces_sample_rate
        self.environment = settings.app_environment

        self.sample_rate = settings.sentry_sample_rate
        self.max_breadcrumbs = settings.sentry_max_breadcrumbs
        self.attach_stacktrace = settings.sentry_attach_stacktrace
        self.integrations = settings.sentry_integrations
        self.additional_params = settings.sentry_additional_params

    def initialize(self) -> None:
        if not self.ready:
            return

        sentry_sdk.init(
            dsn=self.dsn,
            sample_rate=self.sample_rate,
            traces_sample_rate=self.traces_sample_rate,
            environment=self.environment,
            max_breadcrumbs=self.max_breadcrumbs,
            attach_stacktrace=self.attach_stacktrace,
            integrations=self.integrations,
            **self.additional_params,
        )

    def teardown(self) -> None:
        pass

    @property
    def ready(self) -> bool:
        return bool(self.dsn)
