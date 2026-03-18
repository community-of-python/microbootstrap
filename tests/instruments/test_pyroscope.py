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


class TestPyroscopeInstrument:
    @pytest.fixture
    def minimal_pyroscope_config(self) -> PyroscopeConfig:
        return PyroscopeConfig(pyroscope_endpoint=pydantic.HttpUrl("http://localhost:4040"))

    def test_ok(self, minimal_pyroscope_config: PyroscopeConfig) -> None:
        instrument = PyroscopeInstrument(minimal_pyroscope_config)
        assert instrument.is_ready()
        instrument.bootstrap()
        instrument.teardown()

    def test_not_ready(self) -> None:
        instrument = PyroscopeInstrument(PyroscopeConfig(pyroscope_endpoint=None))
        assert not instrument.is_ready()

    def test_opentelemetry_includes_pyroscope(
        self, monkeypatch: pytest.MonkeyPatch, minimal_opentelemetry_config: OpentelemetryConfig
    ) -> None:
        monkeypatch.setattr("opentelemetry.sdk.trace.TracerProvider.shutdown", Mock())
        monkeypatch.setattr(
            "pyroscope.add_thread_tag", add_thread_tag_mock := Mock(side_effect=pyroscope.add_thread_tag)
        )
        monkeypatch.setattr(
            "pyroscope.remove_thread_tag", remove_thread_tag_mock := Mock(side_effect=pyroscope.remove_thread_tag)
        )

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
