default: install lint test

test *args:
  poetry run pytest {{ args }}

install:
  poetry install --sync --no-root --all-extras

lint:
  poetry run ruff format
  poetry run ruff check --fix
  poetry run mypy .

lint-ci:
  poetry run ruff format --check
  poetry run ruff check --no-fix
  poetry run mypy .
