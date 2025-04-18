import pydantic
import pytest

from microbootstrap.instruments.opentelemetry_instrument import OpentelemetryConfig, OpentelemetryInstrument
from microbootstrap.instruments.pyroscope_instrument import PyroscopeConfig, PyroscopeInstrument


try:
    from pyroscope.otel import PyroscopeSpanProcessor  # type: ignore[import-untyped]
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

    def test_opentelemetry_includes_pyroscope(self) -> None:
        otel_instrument = OpentelemetryInstrument(
            OpentelemetryConfig(pyroscope_endpoint=pydantic.HttpUrl("http://localhost:4040"))
        )
        otel_instrument.bootstrap()
        assert PyroscopeSpanProcessor in {
            type(one_span_processor)
            for one_span_processor in otel_instrument.tracer_provider._active_span_processor._span_processors  # noqa: SLF001
        }
