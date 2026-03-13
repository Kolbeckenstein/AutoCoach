# Monorepo Structure

This repository is organised as a monorepo. Each service lives in its own top-level
directory with its own tooling, dependencies, and tests. Shared infrastructure
(docker-compose, devcontainer) lives at the root.

## Directory Layout

```
/                                   ← repo root
├── .devcontainer/                  ← devcontainer config (shared across all services)
│   ├── devcontainer.json
│   ├── docker-compose.yml          ← orchestrates Postgres, Redis, Qdrant
│   └── Dockerfile
├── backend/                        ← Python FastAPI application
│   ├── src/autocoach/              ← application source (src layout)
│   ├── tests/                      ← pytest test suite
│   ├── archive-old-implementation/ ← reference only, not production code
│   ├── pyproject.toml              ← Python deps, ruff/mypy/pytest config
│   ├── Makefile                    ← backend-specific dev commands
│   ├── .pre-commit-config.yaml
│   ├── .env.example
│   └── uv.lock
├── web/                            ← (future) Next.js frontend
├── mobile/                         ← (future) React Native / Flutter
├── ml/                             ← (future) training code, model fine-tuning
│   └── pyproject.toml              ← separate Python package (heavy GPU deps)
├── infra/                          ← (future) Pulumi infrastructure as code
├── docs/                           ← architecture and planning docs (shared)
├── Makefile                        ← root-level, delegates to sub-projects
└── README.md
```

## Principles

**Each service is self-contained.** `backend/` has its own `pyproject.toml`, virtual
environment (`.venv/`), and test suite. Adding `web/` or `ml/` does not affect the
backend's dependency tree.

**`ml/` is separate from `backend/`.** Training dependencies (PyTorch, MotionBERT,
large model weights) are GPU-specific and not needed in the serving stack. A separate
`ml/pyproject.toml` keeps `backend/` lean and deployable without a CUDA environment.

**Infrastructure is shared.** `docker-compose.yml` and `.devcontainer/` sit at the
root because Postgres, Redis, and Qdrant are consumed by multiple services. The root
`Makefile` exposes `docker-up` / `docker-down` for convenience.

**`docs/` is shared.** Architecture decisions, implementation plans, and ADRs
(Architecture Decision Records) live at the root `docs/` and describe the system
as a whole, not any single service.

## Adding a New Service

1. Create `<service>/` at the repo root.
2. Add its own tooling (`package.json`, `pyproject.toml`, etc.) inside that directory.
3. Add a `<service>-*` target group to the root `Makefile` that delegates with
   `$(MAKE) -C <service> <target>`.
4. If the service needs new infrastructure (a new database, a queue), add it to
   `.devcontainer/docker-compose.yml` and forward any new ports in `devcontainer.json`.

## Developer Workflow

Most backend work is done from the `backend/` directory:

```sh
cd backend
uv run pytest -m unit          # fast unit tests
uv run pytest -m integration   # live API / filesystem tests
uv run ruff check src/ tests/  # lint
uv run mypy src/               # type check
```

Or use the delegating targets from the repo root:

```sh
make backend-test-unit
make backend-check-all
make docker-up
```
