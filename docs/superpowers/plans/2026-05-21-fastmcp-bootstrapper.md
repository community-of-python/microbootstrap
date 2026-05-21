# FastMCP Bootstrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FastMCP bootstrapper with settings, config, exports, docs, examples, and tests.

**Architecture:** Follow the existing `ApplicationBootstrapper` pattern. Return a native `fastmcp.FastMCP` server and
keep HTTP app options in config so callers can create ASGI apps when needed.

**Tech Stack:** Python 3.10+, pydantic-settings, pytest, uv, FastMCP optional dependency.

---

### Task 1: Add failing tests

**Files:**
- Create: `tests/bootstrappers/test_fastmcp.py`

- [ ] Write tests that import `FastMCP`, build a bootstrapper, assert service metadata reaches the server, assert
      application config merges, and assert instrument configuration works.
- [ ] Run `uv run pytest tests/bootstrappers/test_fastmcp.py -q` and verify the tests fail because the module does
      not exist yet.

### Task 2: Add config, settings, bootstrapper, and exports

**Files:**
- Create: `microbootstrap/config/fastmcp.py`
- Create: `microbootstrap/bootstrappers/fastmcp.py`
- Modify: `microbootstrap/settings.py`
- Modify: `microbootstrap/__init__.py`

- [ ] Add `FastMcpConfig` with FastMCP constructor options and HTTP app options.
- [ ] Add `FastMcpSettings`.
- [ ] Add `FastMcpBootstrapper`.
- [ ] Export `FastMcpSettings`.
- [ ] Run the FastMCP bootstrapper tests and verify they pass.

### Task 3: Add packaging, docs, and example

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Create: `examples/fastmcp_app.py`

- [ ] Add the `fastmcp` optional dependency group.
- [ ] Document installation and quickstart usage.
- [ ] Add an example FastMCP app with one tool.

### Task 4: Verify

- [ ] Run `uv run pytest tests/bootstrappers/test_fastmcp.py tests/test_settings.py -q`.
- [ ] Run `just lint`.
