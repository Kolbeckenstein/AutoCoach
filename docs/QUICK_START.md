# AutoCoach - Quick Start Guide

**Status:** Planning Complete → Ready for Phase 1 Implementation

---

## 📚 Documentation Overview

| Document | Purpose |
|----------|---------|
| [README.md](../README.md) | Project overview and quick reference |
| [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) | High-level decisions and rationale |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Detailed system design (33 pages) |
| [PERFORMANCE.md](PERFORMANCE.md) | Optimization strategy and benchmarks |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Phased roadmap with code examples |

---

## 🎯 Project Goals

Build an AI-powered workout form coach that:
- Costs <$0.01 per analysis
- Processes videos in <3 seconds
- Provides personalized feedback using community knowledge
- Works for squat, bench press, deadlift (expandable)

---

## 🏗️ System Architecture (TL;DR)

```
User Video → MediaPipe Pose → Biomechanics → Safety Rules → Vector Search → LLM → Coaching
    ↓            (FREE)        (FREE)         (FREE)        (FREE)      ($$$)      ↓
  Upload       <1s extract   <0.1s calc     <0.1s check   <0.05s search $0.003   Results
```

**Key Insight:** Only LLM calls cost money. Everything else is free/local.

---

## 💰 Cost Optimization

| Strategy | Impact | Implementation |
|----------|--------|----------------|
| Semantic caching | 30-50% cost reduction | Redis + rounded features |
| Skip LLM for good form | 20-30% cost reduction | Rule-based pre-check |
| Use cheaper models | 50% cost reduction | Haiku/GPT-4o-mini vs Opus/GPT-4 |
| Optimize prompts | 50% token reduction | Concise outputs |
| **Combined** | **80% cost reduction** | **$0.015 → $0.003** |

---

## 🛠️ Tech Stack

**Backend:**
- Python 3.11+ (FastAPI, Celery)
- PostgreSQL (metadata) + Qdrant (vectors)
- Redis (cache + queue)

**ML/AI:**
- MediaPipe (pose estimation)
- sentence-transformers (embeddings)
- litellm (LLM abstraction)

**Infrastructure:**
- Docker Compose (dev)
- Fly.io or K8s (prod)

---

## 📅 Implementation Timeline

```
Week 1-2:  Phase 1 - Data Collection Pipeline       ← START HERE
            ├─ Fix comment collection bug
            ├─ Build modular scraper
            ├─ Set up database
            └─ Scrape 50+ posts per lift

Week 2-3:  Phase 2 - Pose Processing
            ├─ Extract poses with MediaPipe
            ├─ Calculate biomechanics
            └─ Generate embeddings

Week 3-4:  Phase 3 - RAG System
            ├─ Set up Qdrant
            ├─ Index all lifts
            └─ Build similarity search

Week 4-5:  Phase 4 - LLM Integration
            ├─ Set up litellm
            ├─ Design prompts
            └─ Implement caching

Week 5-7:  Phase 5 - API & Frontend
            ├─ FastAPI backend
            ├─ Celery workers
            └─ Simple web UI

Total: 6-8 weeks → Working prototype
```

---

## 🚀 Getting Started - Phase 1

### Prerequisites
```bash
# Python 3.11+
python --version

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies (coming soon)
pip install -r requirements.txt
```

### Reddit API Credentials
1. Go to https://www.reddit.com/prefs/apps
2. Create new app (script type)
3. Copy client_id and client_secret
4. Set environment variables:
```bash
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
```

### Phase 1 Implementation Steps

**Step 1: Create project structure**
```bash
mkdir -p scraper tests data/{videos,processed}
touch scraper/{__init__.py,config.py,models.py,reddit_scraper.py,storage.py,cli.py}
```

**Step 2: Implement data models** (see IMPLEMENTATION_PLAN.md section 1.2)

**Step 3: Build scraper** (see IMPLEMENTATION_PLAN.md section 1.4)

**Step 4: Test scraping**
```bash
python -m scraper.cli scrape --lift squat --limit 10
sqlite3 data/metadata.db "SELECT COUNT(*) FROM posts;"
```

**Step 5: Scrape full dataset**
```bash
python -m scraper.cli scrape --all --limit 100
```

---

## 📊 Success Criteria - Phase 1

- [x] Scraper collects videos + comments + scores
- [x] Data stored in structured SQLite database
- [x] Incremental scraping (no duplicates)
- [x] At least 50 high-quality posts per lift type
- [x] CLI tool works end-to-end

**How to validate:**
```bash
# Check post counts
sqlite3 data/metadata.db "SELECT lift_type, COUNT(*) FROM posts GROUP BY lift_type;"

# Check comment counts
sqlite3 data/metadata.db "SELECT COUNT(*) FROM comments WHERE score >= 5;"

# Spot check quality
sqlite3 data/metadata.db "SELECT title, post_score FROM posts WHERE lift_type='Squat' LIMIT 5;"
```

---

## 🐛 Known Issues to Fix

### Critical Bug in Old Implementation
**File:** `archive-old-implementation/scraper/scraper.py`
**Lines:** 64-74 collect comments but lines 92-94 only save `{"lift": "Squat"}`

**Impact:** All coaching data was lost!

**Fixed in Phase 1:** New scraper properly saves comments to database.

---

## 🔧 Development Tools

### Recommended IDE Setup
- **VSCode** with Python extension
- **Database viewer** (SQLite Viewer extension)
- **REST client** (Thunder Client for API testing)

### Useful Commands
```bash
# Format code
black .

# Type checking
mypy scraper/

# Run tests
pytest tests/

# Database inspection
sqlite3 data/metadata.db ".tables"
sqlite3 data/metadata.db ".schema posts"

# Redis monitoring (Phase 4+)
redis-cli MONITOR
```

---

## 📖 Key Concepts

### 1. Modular Lift System
Each lift type is a plugin:
```python
class SquatLift(BaseLift):
    critical_keypoints = [23, 24, 25, 26]  # hips, knees
    safety_rules = [KneeValgusRule, DepthRule]

# Register new lifts easily
LIFT_REGISTRY["squat"] = SquatLift
```

### 2. Hybrid RAG
- **Pose similarity:** Find biomechanically similar lifts
- **Comment quality:** Weight by community upvotes
- **LLM synthesis:** Generate personalized coaching

### 3. Cost Optimization Pipeline
```
1. Extract pose (FREE)
2. Check safety rules (FREE) → If dangerous, flag + continue
3. Search similar lifts (FREE)
4. Check cache (FREE) → If hit, return cached coaching
5. Check if "good form" (FREE) → If yes, skip LLM
6. Call LLM ($$$ - only if needed)
7. Cache response (FREE - helps future requests)
```

---

## ❓ FAQ

**Q: Why Python instead of Rust/Go?**
A: The bottlenecks are codec-bound (video I/O) and already compiled (MediaPipe is C++). Python optimization gets us to 1.15s processing time, which is plenty fast.

**Q: Which LLM provider should I use?**
A: Use litellm with Claude Haiku as primary (best quality/cost). It auto-falls back to GPT-4o-mini or Gemini Flash if needed.

**Q: How much will this cost to run?**
A: ~$0.003 per analysis with optimization. For 10,000 analyses/month: ~$30 in LLM costs + ~$100 in compute = ~$130/month.

**Q: Can I add new lift types?**
A: Yes! Just create a new lift class, define safety rules and keypoints, and register it. No changes to core pipeline needed.

**Q: What if MediaPipe doesn't detect the pose?**
A: We return an error to the user asking for better lighting/camera angle. Future: add MMPose as fallback.

---

## 📞 Getting Help

- **Architecture questions:** See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Performance issues:** See [PERFORMANCE.md](PERFORMANCE.md)
- **Implementation details:** See [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- **General overview:** See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)

---

## ✅ Phase 1 Checklist

Ready to start? Follow this checklist:

- [ ] Install Python 3.11+
- [ ] Set up virtual environment
- [ ] Get Reddit API credentials
- [ ] Create project structure
- [ ] Implement Pydantic models
- [ ] Build scraper with comment collection
- [ ] Set up SQLite database
- [ ] Test scraping 10 posts
- [ ] Scrape full dataset (50+ per lift)
- [ ] Validate data quality
- [ ] Move to Phase 2

---

**Let's build! 🏋️**
