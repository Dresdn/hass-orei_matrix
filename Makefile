.PHONY: help install lint format type-check test test-cov clean

help:
	@echo "Orei Matrix Home Assistant Integration - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install      - Install dependencies with UV"
	@echo "  make lint         - Run ruff linter checks"
	@echo "  make format       - Format code with ruff"
	@echo "  make fix          - Fix linting issues automatically"
	@echo "  make type-check   - Run mypy type checking"
	@echo "  make test         - Run pytest tests"
	@echo "  make test-cov     - Run pytest with coverage report"
	@echo "  make quality      - Run lint, format, and type checks"
	@echo "  make clean        - Remove caches and build artifacts"
	@echo ""

install:
	uv sync

lint:
	uv run ruff check custom_components/orei_matrix

format:
	uv run ruff format custom_components/orei_matrix

fix:
	uv run ruff check --fix custom_components/orei_matrix

type-check:
	uv run mypy custom_components/orei_matrix

test:
	uv run pytest

test-cov:
	uv run pytest --cov=custom_components/orei_matrix --cov-report=html --cov-report=term

quality: lint type-check
	@echo "✓ Code quality checks passed!"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name ".coverage" -delete
	rm -rf htmlcov/
	@echo "✓ Cleaned up cache files"
