# AutoCoach

AI-powered workout form coaching using pose estimation, vector similarity search, and LLM-generated feedback.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (modern Python package manager)
- Docker (for services: PostgreSQL, Redis, Qdrant)

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and set up project
git clone <repo-url>
cd AutoCoach
make dev-setup

# Edit .env with your API credentials
vim .env  # Add Reddit API keys, LLM keys, etc.

# Start development services
make docker-up
```

### Development with DevContainer (Recommended)

For the best experience, use the included DevContainer:

1. Open project in VSCode
2. Install "Dev Containers" extension
3. Press `Cmd/Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. Everything is pre-configured! ✨

## 🧪 Testing (TDD Workflow)

We follow Test-Driven Development:

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run with coverage
make test-coverage

# Watch mode (auto-run on file changes)
make test-watch
```

**TDD Cycle:**
1. Write a failing test
2. Run tests and verify failure
3. Implement minimum code to pass
4. Refactor while keeping tests green

## 🛠️ Development Commands

```bash
make help              # Show all commands
make install           # Install dependencies
make test              # Run tests
make lint              # Check code quality
make format            # Format code
make type-check        # Run mypy
make check-all         # Run all checks
```

## 📁 Project Structure

```
AutoCoach/
├── src/autocoach/          # Main package (src layout)
│   ├── scraper/            # Reddit data collection
│   ├── transformer/        # Pose processing
│   ├── rag/                # Vector search & embeddings
│   ├── coaching/           # LLM coaching generation
│   └── api/                # FastAPI backend
├── tests/                  # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── fixtures/           # Test data
├── docs/                   # Documentation
├── .devcontainer/          # DevContainer config
└── pyproject.toml          # Project metadata
```

## 📚 Documentation

- [Architecture](docs/ARCHITECTURE.md) - System design
- [Performance](docs/PERFORMANCE.md) - Optimization strategy
- [Implementation Plan](docs/IMPLEMENTATION_PLAN.md) - Development roadmap
- [Quick Start](docs/QUICK_START.md) - Getting started guide

## 🏗️ Current Status

**Phase 0:** ✅ Repository setup complete
- [x] Modern project structure (src layout)
- [x] DevContainer with all services
- [x] Testing infrastructure (pytest)
- [x] Linting/formatting (ruff)
- [x] Type checking (mypy)
- [x] Pre-commit hooks
- [x] Makefile for common tasks

**Phase 1:** 🚧 Data collection pipeline (in progress)
- [x] Data models (Comment, LiftPost)
- [x] Unit tests for models
- [ ] Reddit scraper implementation
- [ ] Database storage layer
- [ ] CLI tool

## 🧰 Tech Stack

- **Python 3.11+** with type hints
- **uv** - Fast package management
- **FastAPI** - Modern async web framework
- **Pydantic v2** - Data validation
- **pytest** - Testing framework
- **ruff** - Ultra-fast linting & formatting
- **mypy** - Static type checking

**Infrastructure:**
- PostgreSQL (with pgvector)
- Redis
- Qdrant (vector database)
- Docker Compose

## 🤝 Contributing

This project follows TDD practices:

1. Write tests first
2. Make tests pass
3. Refactor
4. Repeat

Run `make check-all` before committing to ensure:
- ✅ Tests pass
- ✅ Code is formatted
- ✅ No linting errors
- ✅ Type checking passes

## 📄 License

MIT

---

**Built with ❤️ for lifters, by lifters**
