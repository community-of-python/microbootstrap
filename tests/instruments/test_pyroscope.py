import typing
from unittest import mock
from unittest.mock import Mock

import fastapi
import pydantic
import pytest
from fastapi.testclient import TestClient as FastAPITestClient

from microbootstrap.bootstrappers.fastapi import FastApiOpentelemetryInstrument
from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig
from microbootstrap.instruments.pyroscope_instrument import PyroscopeConfig, PyroscopeInstrument


try:
    import pyroscope  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    pytest.skip("pyroscope is not installed", allow_module_level=True)


@pytest.fixture
def pyroscope_library_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Mock, Mock, Mock, Mock]:
    configure_mock = Mock()
    shutdown_mock = Mock()
    add_thread_tag_mock = Mock()
    remove_thread_tag_mock = Mock()
    monkeypatch.setattr(pyroscope, "configure", configure_mock)
    monkeypatch.setattr(pyroscope, "shutdown", shutdown_mock)
    monkeypatch.setattr(pyroscope, "add_thread_tag", add_thread_tag_mock)
    monkeypatch.setattr(pyroscope, "remove_thread_tag", remove_thread_tag_mock)
    return configure_mock, shutdown_mock, add_thread_tag_mock, remove_thread_tag_mock


class TestPyroscopeInstrument:
    @pytest.fixture
    def minimal_pyroscope_config(self) -> PyroscopeConfig:
        return PyroscopeConfig(pyroscope_endpoint=pydantic.HttpUrl("http://localhost:4040"))

    def test_ok(
        self,
        minimal_pyroscope_config: PyroscopeConfig,
        pyroscope_library_boundary: tuple[Mock, Mock, Mock, Mock],
    ) -> None:
        configure_mock, shutdown_mock, _, _ = pyroscope_library_boundary
        instrument = PyroscopeInstrument(minimal_pyroscope_config)
        assert instrument.is_ready()
        instrument.bootstrap()
        instrument.teardown()
        configure_mock.assert_called_once_with(
            application_name="micro-service",
            server_address="http://localhost:4040/",
            sample_rate=100,
            tags={},
        )
        shutdown_mock.assert_called_once_with()

    def test_not_ready(self) -> None:
        instrument = PyroscopeInstrument(PyroscopeConfig(pyroscope_endpoint=None))
        assert not instrument.is_ready()

    def test_opentelemetry_includes_pyroscope(
        self,
        minimal_opentelemetry_config: OpentelemetryConfig,
        pyroscope_library_boundary: tuple[Mock, Mock, Mock, Mock],
    ) -> None:
        _, _, add_thread_tag_mock, remove_thread_tag_mock = pyroscope_library_boundary

        minimal_opentelemetry_config.pyroscope_endpoint = pydantic.HttpUrl("http://localhost:4040")

        opentelemetry_instrument: typing.Final = FastApiOpentelemetryInstrument(minimal_opentelemetry_config)
        opentelemetry_instrument.bootstrap()
        fastapi_application: typing.Final = opentelemetry_instrument.bootstrap_after(fastapi.FastAPI())

        @fastapi_application.get("/test-handler")
        async def test_handler() -> None: ...

        FastAPITestClient(app=fastapi_application).get("/test-handler")
        assert (
            add_thread_tag_mock.mock_calls
            == remove_thread_tag_mock.mock_calls
            == [mock.call("span_id", mock.ANY), mock.call("span_name", "GET /test-handler")]
        )
