from __future__ import annotations
import typing

import litestar
import pydantic
import pytest
from litestar.plugins import InitPlugin
from litestar.plugins.pydantic import PydanticPlugin, PydanticSchemaPlugin
from litestar.testing import TestClient

from microbootstrap import LitestarSettings
from microbootstrap.bootstrappers.litestar import LitestarBootstrapper
from microbootstrap.config.litestar import LitestarConfig
from microbootstrap.instruments.base import BaseInstrumentConfig, Instrument
from microbootstrap.instruments.instrument_box import InstrumentBox


if typing.TYPE_CHECKING:
    from litestar._openapi.schema_generation import SchemaCreator
    from litestar.config.app import AppConfig
    from litestar.openapi import spec
    from litestar.plugins import PluginProtocol
    from litestar.typing import FieldDefinition


@typing.final
class CatalogIdentity(pydantic.BaseModel):
    identity: str = pydantic.Field(alias="publicIdentity", description="Public catalog identity.")


def _build_application(
    bootstrapper_type: type[LitestarBootstrapper],
    *,
    metadata_enabled: bool,
    plugins: list[PluginProtocol] | None = None,
) -> litestar.Litestar:
    @litestar.get("/identity", sync_to_thread=False)
    def fetch_identity() -> CatalogIdentity:
        return CatalogIdentity(publicIdentity="catalog-entry")

    return (
        bootstrapper_type(
            LitestarSettings(api_metadata_enabled=metadata_enabled, service_debug=False, health_checks_enabled=False)
        )
        .configure_application(LitestarConfig(route_handlers=[fetch_identity], plugins=plugins or []))
        .bootstrap()
    )


@pytest.mark.parametrize("metadata_enabled", [False, True])
def test_litestar_instrument_alias_policy_matches_the_wire_value(metadata_enabled: bool) -> None:
    @typing.final
    class AliasBootstrapper(LitestarBootstrapper):
        instrument_box = InstrumentBox()

    @AliasBootstrapper.use_instrument()
    @typing.final
    class AliasInstrument(Instrument[BaseInstrumentConfig]):
        instrument_name = "Pydantic alias policy"
        ready_condition = "Always enabled for the catalog"

        @classmethod
        def get_config_type(cls) -> type[BaseInstrumentConfig]:
            return BaseInstrumentConfig

        def is_ready(self) -> bool:
            return True

        def bootstrap_before(self) -> dict[str, list[PluginProtocol]]:
            return {"plugins": [PydanticPlugin(prefer_alias=True)]}

    application: typing.Final = _build_application(AliasBootstrapper, metadata_enabled=metadata_enabled)
    document: typing.Final = application.openapi_schema.to_schema()
    catalog_schema: typing.Final = document["components"]["schemas"]["CatalogIdentity"]
    assert set(catalog_schema["properties"]) == {"publicIdentity"}
    with TestClient(application) as test_client:
        assert test_client.get("/identity").json() == {"publicIdentity": "catalog-entry"}


@pytest.mark.parametrize("metadata_enabled", [False, True])
def test_litestar_init_plugin_keeps_ownership_of_schema_generation(metadata_enabled: bool) -> None:
    @typing.final
    class CatalogSchemaPlugin(PydanticSchemaPlugin):
        def to_openapi_schema(self, field_definition: FieldDefinition, schema_creator: SchemaCreator) -> spec.Schema:
            generated_schema: typing.Final = super().to_openapi_schema(field_definition, schema_creator)
            generated_schema.description = "Application-owned catalog contract."
            return generated_schema

    @typing.final
    class CatalogInitPlugin(InitPlugin):
        def on_app_init(self, app_config: AppConfig) -> AppConfig:
            app_config.plugins.append(CatalogSchemaPlugin())
            return app_config

    application: typing.Final = _build_application(
        LitestarBootstrapper, metadata_enabled=metadata_enabled, plugins=[CatalogInitPlugin()]
    )
    document: typing.Final = application.openapi_schema.to_schema()
    assert document["components"]["schemas"]["CatalogIdentity"]["description"] == "Application-owned catalog contract."
    with TestClient(application) as test_client:
        assert test_client.get("/identity").json() == {"identity": "catalog-entry"}
