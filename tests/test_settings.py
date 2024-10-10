import importlib

import pytest

import microbootstrap.settings


pytestmark = [pytest.mark.usefixtures("reset_reloaded_settings_module")]


@pytest.mark.parametrize("alias", ["SERVICE_NAME", "MY_SERVICE_SERVICE_NAME"])
def test_settings_service_name_aliases(monkeypatch: pytest.MonkeyPatch, alias: str) -> None:
    monkeypatch.setenv("ENVIRONMENT_PREFIX", "MY_SERVICE_")
    monkeypatch.setenv(alias, "my service")
    importlib.reload(microbootstrap.settings)

    settings = microbootstrap.settings.BaseServiceSettings()
    assert settings.service_name == "my service"


def test_settings_service_name_default() -> None:
    settings = microbootstrap.settings.BaseServiceSettings()
    assert settings.service_name == "micro-service"


@pytest.mark.parametrize("alias", ["CI_COMMIT_TAG", "MY_SERVICE_SERVICE_VERSION"])
def test_settings_service_version_aliases(monkeypatch: pytest.MonkeyPatch, alias: str) -> None:
    monkeypatch.setenv("ENVIRONMENT_PREFIX", "MY_SERVICE_")
    monkeypatch.setenv(alias, "1.2.3")
    importlib.reload(microbootstrap.settings)

    settings = microbootstrap.settings.BaseServiceSettings()
    assert settings.service_version == "1.2.3"


def test_settings_service_version_default() -> None:
    settings = microbootstrap.settings.BaseServiceSettings()
    assert settings.service_version == "1.0.0"
