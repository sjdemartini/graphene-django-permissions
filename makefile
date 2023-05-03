sources = graphene_django_permissions

.PHONY: test format lint unittest coverage pre-commit clean
test: format lint unittest

format:
	poetry run black $(sources) tests

lint:
	poetry run ruff .
	poetry run mypy $(sources) tests

unittest:
	poetry run pytest

coverage:
	poetry run pytest --cov=$(sources) --cov-branch --cov-report=term-missing tests

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf .mypy_cache .pytest_cache
	rm -rf *.egg-info
	rm -rf .tox dist site
	rm -rf coverage.xml .coverage
