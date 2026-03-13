# Refactoring Complete: Multi-App Architecture

**Date:** 2026-03-09
**Status:** ✅ Complete - All tests passing

---

## Changes Made

### 1. Restructured for Multiple Applications

**Old Structure:**
```
src/autocoach/
└── scraper/              # Single scraper
    └── models.py
tests/
└── unit/
    └── test_models.py
```

**New Structure:**
```
src/autocoach/
├── scrapers/             # Multiple scrapers
│   ├── reddit/
│   │   ├── __init__.py
│   │   └── models.py
│   └── youtube/          (future)
├── api/                  # FastAPI backend
├── worker/               # Celery workers
├── transformer/          # Pose processing
├── rag/                  # Vector search
├── coaching/             # LLM coaching
└── shared/               # Shared code

apps/
└── web/                  # Frontend (future)

tests/
└── autocoach/            # Mirrors src structure
    └── scrapers/
        └── reddit/
            └── test_models.py
```

### 2. Key Architectural Decisions

**Single Python Package** (`autocoach`)
- ✅ Multiple applications as subpackages
- ✅ Easy code sharing via `autocoach.shared`
- ✅ Simple to develop and deploy
- ✅ Can split into microservices later if needed

**Test Structure Mirrors Source**
- ✅ `src/autocoach/scrapers/reddit/models.py`
- ✅ `tests/autocoach/scrapers/reddit/test_models.py`
- ✅ Easy to find tests for any source file

**No `__init__.py` in Tests**
- ❌ Removed all `__init__.py` from `tests/`
- ✅ Prevents namespace conflicts with actual package
- ✅ pytest can now import `autocoach` correctly

### 3. Import Pattern Changes

**Old:**
```python
from autocoach.scraper.models import Comment, LiftPost
```

**New:**
```python
from autocoach.scrapers.reddit.models import Comment, LiftPost
```

**Benefits:**
- ✅ Clearer which scraper the models belong to
- ✅ Easy to add new scrapers (youtube, instagram, etc.)
- ✅ No naming conflicts

---

## Application Entry Points

### Reddit Scraper
```bash
python -m autocoach.scrapers.reddit.cli scrape --lift squat
```

### API Server (future)
```bash
uvicorn autocoach.api.main:app --reload
```

### Worker (future)
```bash
celery -A autocoach.worker.tasks worker
```

### Web Frontend (future)
```bash
cd apps/web && npm run dev
```

---

## Test Results

**Before Refactoring:**
```bash
✅ 11/11 tests passing
✅ 82% coverage
✅ mypy clean
✅ ruff clean
```

**After Refactoring:**
```bash
✅ 11/11 tests passing
✅ mypy: 10 files checked, no issues
✅ ruff: all checks passed
✅ All quality checks green
```

**Time to Refactor:** ~15 minutes
**Breaking Changes:** Import paths only (easy fix)

---

## Migration Guide

If you have existing code that imports from the old structure:

### For Internal Code

**Find and Replace:**
```bash
# Old pattern
from autocoach.scraper.models import

# New pattern
from autocoach.scrapers.reddit.models import
```

### For Tests

**Old:**
```python
# tests/unit/test_models.py
from autocoach.scraper.models import Comment
```

**New:**
```python
# tests/autocoach/scrapers/reddit/test_models.py
from autocoach.scrapers.reddit.models import Comment
```

---

## Adding New Applications

### New Scraper (e.g., YouTube)

```bash
mkdir -p src/autocoach/scrapers/youtube
touch src/autocoach/scrapers/youtube/{__init__.py,models.py,scraper.py,cli.py}

mkdir -p tests/autocoach/scrapers/youtube
touch tests/autocoach/scrapers/youtube/test_models.py
```

### New Service (e.g., Analytics)

```bash
mkdir -p src/autocoach/analytics
touch src/autocoach/analytics/{__init__.py,metrics.py}

mkdir -p tests/autocoach/analytics
touch tests/autocoach/analytics/test_metrics.py
```

---

## Shared Code Strategy

### When to Add to `shared/`

**Add to `autocoach.shared` when:**
- Used by 2+ services
- Represents core domain concepts
- Needs version stability

**Example:**
```python
# src/autocoach/shared/models.py
class PoseSequence(BaseModel):
    """Used by transformer, rag, api, worker"""
    video_id: str
    frames: list[Frame]
```

### When to Keep Service-Specific

**Keep in service when:**
- Only used by one service
- Service-specific implementation
- Frequently changes

**Example:**
```python
# src/autocoach/scrapers/reddit/models.py
class LiftPost(BaseModel):
    """Reddit-specific post model"""
    id: str  # Reddit post ID format
    video_url: HttpUrl  # Reddit video URL
```

---

## Future: Path to Microservices

If we need to split services later:

### Step 1: Create Separate Packages

```bash
packages/
├── shared/                # autocoach-shared
│   └── src/autocoach_shared/
├── scrapers/              # autocoach-scrapers
│   └── src/autocoach_scrapers/
├── api/                   # autocoach-api
│   └── src/autocoach_api/
└── worker/                # autocoach-worker
    └── src/autocoach_worker/
```

### Step 2: Update Dependencies

```toml
# packages/api/pyproject.toml
dependencies = [
    "autocoach-shared>=1.0.0",
]
```

### Step 3: Deploy Separately

```yaml
# kubernetes or docker-compose
services:
  api:
    image: autocoach/api:latest
  worker:
    image: autocoach/worker:latest
  scraper:
    image: autocoach/scrapers:latest
```

**Current structure makes this split easy when needed!**

---

## Documentation Updates

Updated:
- ✅ [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Comprehensive structure guide
- ✅ [README.md](../README.md) - Updated project structure section
- ✅ Import paths in all code examples

To Update:
- [ ] IMPLEMENTATION_PLAN.md - Update code examples with new import paths
- [ ] ARCHITECTURE.md - Update package structure diagrams

---

## Benefits of This Structure

### Development

- ✅ **Clear separation** - Each service has its own directory
- ✅ **Easy navigation** - Tests mirror source structure
- ✅ **Shared code** - Common models in `shared/`
- ✅ **Type safety** - Full mypy coverage across all services

### Deployment

- ✅ **Single package** - Easy to build and deploy
- ✅ **Flexible** - Can run all in one container or split
- ✅ **Scalable** - Easy to extract services as needed

### Testing

- ✅ **Isolated** - Test each service independently
- ✅ **Fast** - Run only relevant tests during development
- ✅ **Clear** - Test path shows what's being tested

---

## Commands Updated

### Makefile (future updates needed)

```makefile
# Old
test-scraper:
	pytest tests/unit/

# New (to add)
test-reddit-scraper:
	pytest tests/autocoach/scrapers/reddit/

test-api:
	pytest tests/autocoach/api/

test-all:
	pytest tests/
```

---

## Summary

✅ **Restructured** for multi-application architecture
✅ **All tests** passing (11/11)
✅ **Type checking** clean (mypy)
✅ **Linting** clean (ruff)
✅ **Documentation** updated

**Ready to:**
1. Add YouTube scraper
2. Implement Reddit scraper logic
3. Build API service
4. Add more services as needed

**Next:** Continue with Phase 1 - Reddit scraper implementation

---

## Lessons Learned

1. **pytest + package names**: Don't put `__init__.py` in test directories that mirror package names - causes import conflicts

2. **src layout**: The `src/` layout prevents accidental imports from the working directory

3. **editable install**: Always install in editable mode during development: `uv pip install -e .`

4. **Test discovery**: pytest works best when test structure mirrors source structure

---

**Refactoring complete! Architecture ready for scaling.** 🚀
