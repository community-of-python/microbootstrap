# FastMCP Bootstrapper Design

## Goal

Add FastMCP as a first-class microbootstrap target next to FastAPI, Litestar, and FastStream.

## Architecture

The feature introduces `FastMcpBootstrapper`, backed by a focused `FastMcpConfig` dataclass and `FastMcpSettings`
settings model. The bootstrapper creates a `fastmcp.FastMCP` server through the existing
`ApplicationBootstrapper` lifecycle, so common instruments can keep using `bootstrap`, `bootstrap_before`,
`bootstrap_after`, and `teardown`.

FastMCP has two useful surfaces: the native server object and an ASGI app returned by `http_app()`. The bootstrapper
returns the native server object. Callers configure the ASGI HTTP app through FastMCP's own `http_app()` interface.

## Instruments

The first version wires framework-independent instruments that already work without a web framework-specific adapter:
Sentry, Pyroscope, and Logging. FastMCP HTTP custom routes are used for Health checks and Prometheus. OpenTelemetry
needs a FastMCP-specific tracing adapter before it can be added safely.

## Data Flow

`FastMcpSettings` collects service metadata and instrument config from environment variables. `FastMcpBootstrapper`
initializes the configured instruments, merges their bootstrap config with `FastMcpConfig`, creates `fastmcp.FastMCP`,
and returns the server.

## Testing

Tests cover configuration merging, service metadata propagation, instrument configuration, and the HTTP app option
surface without requiring a running MCP transport.
