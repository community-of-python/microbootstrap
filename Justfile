default: install lint test

install:
    uv lock --upgrade
    uv sync --all-extras --frozen

lint:
    uv run ruff format
    uv run ruff check --fix
    uv run mypy .

lint-ci:
    uv run ruff format --check
    uv run ruff check --no-fix
    uv run mypy .

test *args:
    uv run --no-sync pytest {{ args }}

publish:
    rm -rf dist
    uv version $GITHUB_REF_NAME
    uv build
    uv publish --token $PYPI_TOKEN

run-faststream-example *args:
    #!/bin/bash
    trap 'echo; docker rm -f microbootstrap-redis' EXIT
    docker run --name microbootstrap-redis -p 6379:6379 -d redis
    uv run examples/faststream_app.py
