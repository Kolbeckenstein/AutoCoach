# AutoCoach Architecture

**Last Updated:** 2026-03-09
**Status:** Planning Phase

## Executive Summary

AutoCoach is a workout form coaching system that analyzes powerlifting videos and provides AI-generated coaching feedback. The system uses pose estimation, vector similarity search, and LLM synthesis to deliver personalized form corrections based on community knowledge from Reddit's r/formcheck.

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACE                           │
│                     (Web → Mobile later)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Video Upload
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                         API LAYER                               │
│                     FastAPI + Celery                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ Upload API   │  │ Status API   │  │ Results API  │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Task Queue (Redis)
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PROCESSING PIPELINE                          │
│                                                                 │
│  1. Video Preprocessing (FFmpeg)                               │
│     - Compression, format normalization                        │
│                                                                 │
│  2. Pose Estimation (MediaPipe)                                │
│     - Extract 33 landmarks per frame                           │
│     - Calculate biomechanical features                         │
│                                                                 │
│  3. Rep Segmentation                                           │
│     - Identify individual reps                                 │
│     - Phase detection (eccentric/concentric)                   │
│                                                                 │
│  4. Rule-Based Safety Checks                                   │
│     - Dangerous form detection (FREE, no LLM needed)           │
│                                                                 │
│  5. Pose Embedding Generation                                  │
│     - Temporal sequence encoding                               │
│                                                                 │
│  6. Vector Similarity Search (Qdrant)                          │
│     - Find similar lifts from training data                    │
│     - Retrieve highly-rated comments                           │
│                                                                 │
│  7. LLM Synthesis (via litellm)                                │
│     - Generate personalized coaching                           │
│     - Only if issues found OR user requests                    │
│     - Cached for similar patterns                              │
│                                                                 │
│  8. Video Overlay Generation                                   │
│     - User pose + ideal pose comparison                        │
│     - Highlighted problem areas                                │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Results
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                      DATA STORAGE                               │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  PostgreSQL  │  │   Qdrant     │  │  MinIO/S3    │         │
│  │  (Metadata)  │  │  (Vectors)   │  │  (Videos)    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Data Collection Layer

**Purpose:** Scrape and curate training data from Reddit and other sources

**Components:**
- **Reddit Scraper** (PRAW)
  - Scrapes r/formcheck by lift flair
  - Collects videos + comments + upvote scores
  - Incremental updates (tracks processed posts)

- **YouTube Scraper** (yt-dlp) - Future
  - High-quality coaching channels
  - Gold standard technique videos

- **Data Storage**
  - Videos: File storage (organized by lift type)
  - Metadata: PostgreSQL (posts, comments, scores)
  - Processed Poses: JSON/Parquet files

**Schema:**
```sql
CREATE TABLE posts (
    id TEXT PRIMARY KEY,
    lift_type TEXT NOT NULL,
    title TEXT,
    video_url TEXT,
    video_path TEXT,
    created_utc TIMESTAMP,
    author TEXT,
    score INTEGER
);

CREATE TABLE comments (
    id TEXT PRIMARY KEY,
    post_id TEXT REFERENCES posts(id),
    body TEXT NOT NULL,
    score INTEGER,
    author TEXT,
    created_utc TIMESTAMP
);

CREATE TABLE pose_data (
    id UUID PRIMARY KEY,
    post_id TEXT REFERENCES posts(id),
    frames JSONB,  -- Array of frame data
    embedding VECTOR(512),  -- For pgvector extension
    created_at TIMESTAMP
);
```

### 2. Pose Processing Pipeline

**MediaPipe Pose Estimation:**
- Input: Video file
- Output: 33 landmarks × N frames
- Features extracted:
  - Joint positions (x, y, z, visibility)
  - Joint angles (hip, knee, ankle, shoulder, elbow)
  - Bar path (wrist tracking as proxy)
  - Tempo/velocity
  - Depth/range of motion

**Biomechanical Analysis (Lift-Specific):**

**Squat:**
- Hip angle at bottom
- Knee tracking (valgus/varus)
- Back angle
- Depth (hip crease vs knee)

**Bench Press:**
- Bar path (J-curve)
- Elbow angle
- Shoulder position
- Touch point on chest

**Deadlift:**
- Back angle
- Hip hinge pattern
- Bar distance from shins
- Lockout position

### 3. Modular Lift System

**Base Architecture:**
```python
from abc import ABC, abstractmethod
from typing import List, Dict

class BaseLift(ABC):
    """Abstract base class for lift types"""

    lift_name: str
    critical_keypoints: List[int]  # Subset of 33 landmarks

    @abstractmethod
    def check_safety(self, pose_sequence) -> List[SafetyIssue]:
        """Rule-based safety checks"""
        pass

    @abstractmethod
    def extract_features(self, pose_sequence) -> Dict:
        """Extract biomechanical features"""
        pass

    @abstractmethod
    def generate_ideal_pose(self, user_pose) -> PoseSequence:
        """Generate comparison overlay"""
        pass

class SquatLift(BaseLift):
    lift_name = "Squat"
    critical_keypoints = [11, 12, 23, 24, 25, 26, 27, 28]  # Shoulders, hips, knees, ankles

    def check_safety(self, pose_sequence):
        issues = []
        # Check for knee valgus
        # Check for excessive back rounding
        # Check depth
        return issues
```

**Lift Registry:**
```python
LIFT_REGISTRY = {
    "Squat": SquatLift,
    "Bench Press": BenchLift,
    "Deadlift": DeadliftLift,
}

def get_lift_handler(lift_type: str) -> BaseLift:
    return LIFT_REGISTRY[lift_type]()
```

### 4. Vector Database & RAG

**Qdrant Schema:**
```python
{
    "collection_name": "lift_coaching",
    "vectors": {
        "pose": 512,      # Pose sequence embedding
        "comment": 384    # Text embedding (all-MiniLM-L6-v2)
    },
    "payload": {
        "lift_type": "Squat",
        "video_id": "abc123",
        "comments": [
            {
                "text": "Your knees are caving in...",
                "score": 42,
                "author": "coach_mike"
            }
        ],
        "pose_features": {
            "hip_angle_min": 87.3,
            "knee_tracking": "valgus_moderate",
            "depth": "parallel"
        }
    }
}
```

**Retrieval Strategy:**
1. **Pose similarity** (cosine distance on pose embeddings)
2. **Filtered by lift type** (mandatory)
3. **Weighted by comment scores** (upvotes)
4. **Retrieve top-K** (K=5-10)

**Hybrid Search:**
```python
results = qdrant_client.search(
    collection_name="lift_coaching",
    query_vector=user_pose_embedding,
    query_filter={
        "must": [
            {"key": "lift_type", "match": {"value": "Squat"}},
            {"key": "comments[].score", "range": {"gte": 5}}
        ]
    },
    limit=10,
    with_payload=True
)
```

### 5. LLM Integration (via litellm)

**Provider Configuration:**
```python
import litellm

litellm.set_verbose = True  # For debugging

# Fallback chain: Haiku → GPT-4o-mini → Gemini Flash
PROVIDER_CONFIG = [
    {"model": "claude-3-haiku-20240307", "max_tokens": 1000},
    {"model": "gpt-4o-mini", "max_tokens": 1000},
    {"model": "gemini/gemini-1.5-flash", "max_tokens": 1000},
]

async def generate_coaching(
    user_pose_features: Dict,
    similar_lifts: List[Dict],
    issues: List[SafetyIssue]
) -> str:
    """Generate coaching feedback with fallback"""

    prompt = construct_coaching_prompt(
        user_pose_features,
        similar_lifts,
        issues
    )

    for config in PROVIDER_CONFIG:
        try:
            response = await litellm.acompletion(
                model=config["model"],
                messages=[{"role": "user", "content": prompt}],
                max_tokens=config["max_tokens"],
                temperature=0.7
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Provider {config['model']} failed: {e}")
            continue

    raise Exception("All LLM providers failed")
```

**Prompt Template:**
```python
COACHING_PROMPT = """
You are an experienced powerlifting coach analyzing a {lift_type}.

USER'S LIFT ANALYSIS:
- Hip angle at bottom: {hip_angle}°
- Knee tracking: {knee_tracking}
- Depth: {depth}
- Bar path deviation: {bar_path_deviation}

SAFETY ISSUES DETECTED:
{safety_issues}

SIMILAR LIFTS FROM COMMUNITY:
{similar_lifts_comments}

Provide concise, actionable coaching feedback:
1. Prioritize safety issues first
2. Reference specific biomechanical measurements
3. Suggest 2-3 concrete cues to improve form
4. Mention relevant comments from similar lifts

Keep response under 200 words.
"""
```

**Caching Strategy:**
```python
import hashlib

def cache_key(pose_features: Dict, issues: List) -> str:
    """Generate cache key from pose features"""
    canonical = json.dumps(pose_features, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

# Redis caching
cache = redis.Redis()
ttl = 7 * 24 * 3600  # 7 days

cached = cache.get(key)
if cached:
    return json.loads(cached)

response = await generate_coaching(...)
cache.setex(key, ttl, json.dumps(response))
```

### 6. API Layer

**FastAPI Endpoints:**
```python
from fastapi import FastAPI, UploadFile, BackgroundTasks
from celery import Celery

app = FastAPI()
celery = Celery('autocoach', broker='redis://localhost:6379')

@app.post("/api/v1/analyze")
async def analyze_video(
    video: UploadFile,
    lift_type: str,
    background_tasks: BackgroundTasks
):
    """Upload video for analysis"""

    # Save video
    video_id = generate_id()
    video_path = save_video(video, video_id)

    # Queue processing task
    task = celery.send_task(
        'process_video',
        args=[video_id, video_path, lift_type]
    )

    return {
        "video_id": video_id,
        "task_id": task.id,
        "status": "queued"
    }

@app.get("/api/v1/status/{task_id}")
async def get_status(task_id: str):
    """Check processing status"""
    task = celery.AsyncResult(task_id)
    return {
        "status": task.state,
        "progress": task.info.get('progress', 0) if task.info else 0
    }

@app.get("/api/v1/results/{video_id}")
async def get_results(video_id: str):
    """Get analysis results"""
    results = load_results(video_id)
    return {
        "video_id": video_id,
        "lift_type": results.lift_type,
        "safety_issues": results.safety_issues,
        "coaching_feedback": results.coaching_text,
        "overlay_video_url": results.overlay_url,
        "pose_metrics": results.pose_features
    }
```

**Celery Worker:**
```python
@celery.task(bind=True)
def process_video(self, video_id: str, video_path: str, lift_type: str):
    """Process video in background"""

    # Update progress
    self.update_state(state='PROGRESS', meta={'progress': 10})

    # 1. Pose estimation
    pose_sequence = extract_poses(video_path)
    self.update_state(state='PROGRESS', meta={'progress': 30})

    # 2. Feature extraction
    lift_handler = get_lift_handler(lift_type)
    features = lift_handler.extract_features(pose_sequence)
    self.update_state(state='PROGRESS', meta={'progress': 50})

    # 3. Safety checks
    safety_issues = lift_handler.check_safety(pose_sequence)
    self.update_state(state='PROGRESS', meta={'progress': 60})

    # 4. Vector search
    similar_lifts = search_similar_lifts(features, lift_type)
    self.update_state(state='PROGRESS', meta={'progress': 70})

    # 5. LLM coaching (if needed)
    if safety_issues or user_requested_feedback:
        coaching = generate_coaching(features, similar_lifts, safety_issues)
    else:
        coaching = "Form looks good! No major issues detected."
    self.update_state(state='PROGRESS', meta={'progress': 85})

    # 6. Generate overlay video
    overlay_path = generate_overlay(video_path, pose_sequence, features)
    self.update_state(state='PROGRESS', meta={'progress': 95})

    # 7. Save results
    save_results(video_id, {
        "coaching": coaching,
        "safety_issues": safety_issues,
        "features": features,
        "overlay_url": upload_to_storage(overlay_path)
    })

    return {"status": "complete", "video_id": video_id}
```

---

## Technology Stack

### Backend
- **Language:** Python 3.11+
- **API Framework:** FastAPI
- **Task Queue:** Celery + Redis
- **Database:** PostgreSQL (metadata)
- **Vector DB:** Qdrant (self-hosted or cloud)
- **Video Storage:** MinIO (self-hosted) or S3
- **LLM Router:** litellm

### ML/AI
- **Pose Estimation:** MediaPipe (primary), MMPose (fallback)
- **Video Processing:** OpenCV, FFmpeg
- **Text Embeddings:** sentence-transformers (all-MiniLM-L6-v2)
- **Pose Embeddings:** Custom LSTM/Transformer
- **LLM Providers:** Claude Haiku, GPT-4o-mini, Gemini Flash

### Frontend (Phase 5)
- **Web:** Next.js + TailwindCSS
- **Video Player:** React Player
- **Pose Visualization:** Canvas API / three.js
- **Mobile:** React Native (later)

### Infrastructure
- **Development:** Docker Compose
- **Production:** Kubernetes or Fly.io
- **Monitoring:** Prometheus + Grafana
- **Logging:** ELK Stack or Loki

---

## Deployment Architecture

### Development
```yaml
version: '3.8'
services:
  api:
    build: ./api
    ports:
      - "8000:8000"

  celery_worker:
    build: ./api
    command: celery -A app.celery worker

  redis:
    image: redis:7-alpine

  postgres:
    image: postgres:15

  qdrant:
    image: qdrant/qdrant:latest

  minio:
    image: minio/minio:latest
```

### Production (Cost-Optimized)
- **API:** 2x small instances (auto-scaling)
- **Celery Workers:** 4x CPU-optimized instances
- **Redis:** Managed service (Redis Cloud free tier)
- **PostgreSQL:** Managed service (Neon/Supabase free tier)
- **Qdrant:** Self-hosted on 1x instance (or Qdrant Cloud)
- **Storage:** S3 or Cloudflare R2
- **CDN:** Cloudflare (free)

**Estimated Monthly Cost (1000 users, 10 analyses/user):**
- Compute: $50-100
- Database: $0-20 (free tiers)
- Storage: $10-20
- LLM API: $100-200 (with caching)
- **Total: ~$200-300/month**

---

## Security Considerations

1. **Video Upload:**
   - Max file size: 100MB
   - Allowed formats: mp4, mov, avi
   - Virus scanning (ClamAV)
   - Rate limiting

2. **Data Privacy:**
   - Videos deleted after 30 days
   - No PII collected
   - Optional user accounts (not required)

3. **API Security:**
   - Rate limiting (10 requests/hour for free tier)
   - API keys for authenticated users
   - Input validation (Pydantic)

4. **LLM Prompt Injection:**
   - Sanitize user inputs
   - Use system prompts with boundaries
   - Monitor for abuse

---

## Monitoring & Observability

**Key Metrics:**
- Processing time per video (p50, p95, p99)
- LLM token usage & cost
- Error rates by component
- Queue depth & worker utilization

**Alerts:**
- Processing time > 30s
- Error rate > 5%
- LLM cost spike
- Queue depth > 100

---

## Future Enhancements

**Phase 6+:**
- Multi-angle analysis (front + side views)
- Real-time feedback (mobile app with camera)
- Progressive overload tracking
- Social features (share analyses, leaderboards)
- Custom coaching plans
- Integration with training apps (Strong, JEFIT)

---

## References

- FormCoach Paper: https://arxiv.org/abs/2508.07501
- MediaPipe: https://google.github.io/mediapipe/
- Qdrant: https://qdrant.tech/
- litellm: https://github.com/BerriAI/litellm
