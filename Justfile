default: install lint test

# run pytest with arguments
test *args:
  poetry run pytest {{ args }}

# install local dependencies
install:
  poetry install --sync --no-root --all-extras

# run linters
lint:
  poetry run ruff format
  poetry run ruff check --fix
  poetry run mypy .
