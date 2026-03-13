.PHONY: help install test lint format type-check clean dev-setup

help:  ## Show this help message
	@echo "AutoCoach Development Commands"
	@echo "=============================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies with uv
	uv sync --all-extras

dev-setup: install  ## Set up development environment
	uv run pre-commit install
	cp .env.example .env
	@echo "✓ Development environment ready!"
	@echo "  Edit .env with your API credentials"

test:  ## Run tests
	uv run pytest

test-watch:  ## Run tests in watch mode
	uv run pytest-watch

test-unit:  ## Run only unit tests
	uv run pytest -m unit

test-integration:  ## Run only integration tests
	uv run pytest -m integration

test-coverage:  ## Run tests with coverage report
	uv run pytest --cov --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

lint:  ## Run ruff linter
	uv run ruff check src/ tests/

lint-fix:  ## Fix auto-fixable linting issues
	uv run ruff check --fix src/ tests/

format:  ## Format code with ruff
	uv run ruff format src/ tests/

format-check:  ## Check code formatting
	uv run ruff format --check src/ tests/

type-check:  ## Run mypy type checker
	uv run mypy src/

pipeline-scrape:  ## Run the Reddit scraper (usage: make pipeline-scrape ARGS="--limit 10")
	uv run autocoach pipeline scrape $(ARGS)

pipeline-pose:  ## Run pose processing on a video (usage: make pipeline-pose ARGS="path/to/video.mp4")
	uv run autocoach pipeline pose-process $(ARGS)

download-models:  ## Download MediaPipe PoseLandmarker model file
	@mkdir -p models
	@echo "Downloading pose_landmarker_full.task..."
	@curl -fL \
	  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task" \
	  -o models/pose_landmarker_full.task
	@echo "✓ Model saved to backend/models/pose_landmarker_full.task"

check-all: lint format-check type-check test  ## Run all checks

clean:  ## Clean up generated files
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

docker-up:  ## Start development services (postgres, redis, qdrant)
	docker-compose -f ../.devcontainer/docker-compose.yml up -d postgres redis qdrant

docker-down:  ## Stop development services
	docker-compose -f ../.devcontainer/docker-compose.yml down

docker-logs:  ## Show service logs
	docker-compose -f ../.devcontainer/docker-compose.yml logs -f

db-migrate:  ## Run database migrations
	uv run alembic upgrade head

db-rollback:  ## Rollback last migration
	uv run alembic downgrade -1

db-reset:  ## Reset database (destructive!)
	docker-compose -f ../.devcontainer/docker-compose.yml down -v
	docker-compose -f ../.devcontainer/docker-compose.yml up -d postgres
	sleep 2
	uv run alembic upgrade head
