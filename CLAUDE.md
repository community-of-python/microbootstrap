# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
just install          # Install all deps (uv lock --upgrade + uv sync --all-extras)
just lint             # Format and lint with fixes (ruff format, ruff check --fix, mypy)
just lint-ci          # Lint check without fixes
just test             # Run full test suite with coverage
just test tests/path/to/test_file.py   # Run single test file
just test -k test_name                 # Run tests matching a name
```

## Architecture

Microbootstrap auto-wires production instrumentation (observability, logging, tracing, etc.) into Python web/messaging frameworks via a settings-driven plugin system.

### Core concepts

**Instruments** (`microbootstrap/instruments/`) — Independent plugins for each tool (Sentry, OpenTelemetry, Prometheus, structlog, Pyroscope, Swagger, CORS, health checks). Each instrument has:
- A config class extending `BaseInstrumentConfig` (Pydantic model)
- `is_ready()` — gating check before activation
- `bootstrap_before()` → returns `dict` merged into app constructor kwargs
- `bootstrap()` — side-effectful initialization
- `bootstrap_after(app)` — post-construction setup (middleware, routes)

**Bootstrappers** (`microbootstrap/bootstrappers/`) — Framework-specific orchestrators for Litestar, FastAPI, FastStream, and a framework-agnostic `InstrumentsSetupper`. They:
1. Accept a settings object and extract per-instrument configs
2. Build the framework app by merging all `bootstrap_before()` dicts with user-supplied config
3. Call `bootstrap_after(app)` on each instrument
4. Register instruments via the `@Bootstrapper.use_instrument()` class decorator

**Settings** (`microbootstrap/settings.py`) — Pydantic Settings classes combining `BaseServiceSettings` with per-instrument config mixins. Each framework (`LitestarSettings`, `FastApiSettings`, `FastStreamSettings`) inherits all relevant config mixins. Reads from env vars, with optional `ENVIRONMENT_PREFIX` namespacing.

**Config merging** (`microbootstrap/helpers.py`) — When merging instrument dicts with user-supplied framework config: scalars are overridden, containers (dict/list/set/tuple) are deep-merged/extended.

### Adding a new instrument

1. Create config class extending `BaseInstrumentConfig` in `instruments/`
2. Create instrument class extending `Instrument[YourConfig]` — implement `is_ready`, `bootstrap`, `bootstrap_before`, `bootstrap_after`
3. Create framework-specific subclasses extending both the base instrument and `LitestarInstrument`/`FastApiInstrument`/etc.
4. Register each with `@LitestarBootstrapper.use_instrument()` (and other frameworks as needed)
5. Add config mixin to the relevant Settings classes

### Key constraints

- Strict mypy — all code must type-check cleanly
- Python 3.10–3.14 support required; avoid 3.11+ syntax
- All instrument extras are optional deps; use `TYPE_CHECKING` guards where needed
