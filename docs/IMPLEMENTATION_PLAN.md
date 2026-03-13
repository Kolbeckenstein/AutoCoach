# AutoCoach Implementation Plan

**Last Updated:** 2026-03-09
**Status:** Ready to Start

---

## Overview

This document outlines the phased implementation plan for AutoCoach, a cost-effective workout form coaching system. The plan is designed to deliver incremental value while maintaining flexibility for iteration based on learnings.

---

## Development Principles

1. **Incremental Delivery** - Each phase produces working, testable functionality
2. **Cost-First** - Optimize for operational cost from day one
3. **Modularity** - Easy to add new lift types and features
4. **Quality Data** - Prioritize data quality over quantity
5. **Test Early** - Validate assumptions with real data ASAP

---

## Phase Breakdown

### Phase 1: Data Collection Pipeline (Weeks 1-2)
**Goal:** Build robust, modular scraper that collects high-quality training data

**Critical Fix:**
- Current scraper collects comments but doesn't save them (lines 64-74 in old scraper.py)
- This is the most valuable coaching data!

**Deliverables:**

#### 1.1 Project Structure

Full backend module layout (`src/autocoach/`):

```
src/autocoach/
├── __init__.py
├── config.py                  # App-wide Pydantic settings (DB URL, Redis URL, blob config, log level)
├── cli.py                     # Entry point: autocoach CLI (referenced in pyproject.toml)
├── api/                       # FastAPI routes + request/response schemas
├── blob/                      # Object storage abstraction
│   ├── __init__.py
│   ├── protocol.py            # BlobStorage Protocol: upload(), download(), get_url()
│   ├── local.py               # Local filesystem backend (dev / Phase 1)
│   └── s3.py                  # S3-compatible backend (R2 / S3 / GCS — Phase 3+)
├── coaching/                  # LLM synthesis, prompt building; calls rag/, optionally pose/
├── db/                        # SQLAlchemy ORM models, Alembic migrations, async session factory
├── pose/                      # Video → normalized pose sequence → biomechanical features
│                              #   (renamed from transformer — avoids ML architecture ambiguity)
├── rag/                       # Qdrant client, indexing, ANN retrieval
├── scrapers/
│   └── reddit/
│       ├── __init__.py
│       ├── config.py          # RedditConfig + ScrapeConfig (Pydantic settings)
│       ├── models.py          # Comment, LiftPost
│       ├── client.py          # PRAW wrapper
│       ├── downloader.py      # Video download (httpx streaming)
│       ├── storage.py         # JSON-based persistence + seen-ID manifest
│       └── scraper.py         # Orchestrator (client + downloader + storage)
├── shared/                    # Cross-cutting: exceptions, logging helpers, types
└── worker/                    # Celery task definitions
                               #   batch scrape: scrapers/ → pose/ → rag/
                               #   user upload:  pose/ → rag/ → coaching/ (triggered by api/)
```

**Persistence split — why `db/` and `blob/` are separate modules:**

Videos are not stored in Postgres. Object storage (S3-compatible bucket) is ~10x cheaper per GB, scales independently, and plugs into a CDN for delivery. Postgres stores everything *about* a video; the blob store holds the bytes.

| Data | Where |
|---|---|
| Post metadata, comments, job state | `db/` → PostgreSQL |
| Video files | `blob/` → local filesystem (dev), S3/R2 (prod) |
| Pose sequences (if large) | `blob/` as JSON/binary objects |
| Vectors | Qdrant (via `rag/`) |

`blob/` exposes a `BlobStorage` protocol so the backend is swappable at config time with no code changes. `video_key` on `LiftPost` (formerly `video_path`) is an opaque string — a relative path for the local backend, an object key for S3/R2. The blob module resolves it to a URL or byte stream; callers never handle raw paths or presigned URL logic.

`db/` and `blob/` are kept separate because they solve different problems: schema evolution + relational queries vs. large-object streaming. A unified `storage/` wrapper would hide nothing from callers while making both layers harder to test in isolation.

**Dependency flow:**
- `api` → enqueues worker tasks; calls `coaching` for synchronous paths
- `coaching` → `rag` (retrieval) + optionally LLM
- `worker` → `scrapers`, `pose`, `rag`, `db`, `blob`
- `rag` → Qdrant
- `db` → PostgreSQL (SQLAlchemy + asyncpg)
- `blob` → local filesystem or S3-compatible bucket (provider chosen at deploy time)
- `shared` → imported by all; imports nothing internal

#### 1.2 Data Models (Pydantic)
```python
# scraper/models.py
from pydantic import BaseModel, HttpUrl
from datetime import datetime
from typing import List, Optional

class Comment(BaseModel):
    id: str
    body: str
    score: int
    author: str
    created_utc: datetime
    is_top_level: bool

class LiftPost(BaseModel):
    id: str
    lift_type: str
    title: str
    video_url: HttpUrl
    video_path: Optional[str] = None
    created_utc: datetime
    author: str
    post_score: int
    comments: List[Comment] = []

    def top_comments(self, min_score: int = 5) -> List[Comment]:
        """Get highly-rated comments"""
        return [c for c in self.comments if c.score >= min_score]
```

#### 1.3 Modular Lift Registry
```python
# scraper/config.py
from dataclasses import dataclass
from typing import List

@dataclass
class LiftConfig:
    name: str
    reddit_flair: str
    keywords: List[str]  # For filtering quality posts

LIFT_REGISTRY = {
    "squat": LiftConfig(
        name="Squat",
        reddit_flair="Squat",
        keywords=["squat", "depth", "knee"]
    ),
    "bench": LiftConfig(
        name="Bench Press",
        reddit_flair="Bench Press",
        keywords=["bench", "press", "elbow"]
    ),
    "deadlift": LiftConfig(
        name="Deadlift",
        reddit_flair="Deadlift",
        keywords=["deadlift", "back", "hinge"]
    ),
}
```

#### 1.4 Improved Scraper
```python
# scraper/reddit_scraper.py
import praw
from typing import List, Optional
from .models import LiftPost, Comment
from .config import LIFT_REGISTRY
from .storage import Storage

class RedditScraper:
    def __init__(self, client_id: str, client_secret: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent="AutoCoach/2.0"
        )
        self.storage = Storage()

    def scrape_lift(
        self,
        lift_type: str,
        limit: int = 100,
        min_comments: int = 3
    ) -> List[LiftPost]:
        """Scrape posts for a specific lift type"""

        lift_config = LIFT_REGISTRY[lift_type]
        subreddit = self.reddit.subreddit('formcheck')

        posts = subreddit.search(
            f'flair:"{lift_config.reddit_flair}"',
            limit=limit,
            sort='top',
            time_filter='month'
        )

        scraped_posts = []
        for post in posts:
            # Skip if already scraped
            if self.storage.post_exists(post.id):
                continue

            # Extract video URL
            video_url = self._extract_video_url(post)
            if not video_url:
                continue

            # Extract comments
            comments = self._extract_comments(post)

            # Skip if insufficient community feedback
            if len(comments) < min_comments:
                continue

            lift_post = LiftPost(
                id=post.id,
                lift_type=lift_config.name,
                title=post.title,
                video_url=video_url,
                created_utc=datetime.fromtimestamp(post.created_utc),
                author=post.author.name if post.author else "deleted",
                post_score=post.score,
                comments=comments
            )

            scraped_posts.append(lift_post)

        return scraped_posts

    def _extract_comments(self, post) -> List[Comment]:
        """Extract all top-level comments with scores"""
        post.comments.replace_more(limit=0)  # Remove "load more"

        comments = []
        for comment in post.comments:
            if hasattr(comment, 'body'):
                comments.append(Comment(
                    id=comment.id,
                    body=comment.body,
                    score=comment.score,
                    author=comment.author.name if comment.author else "deleted",
                    created_utc=datetime.fromtimestamp(comment.created_utc),
                    is_top_level=True
                ))

        return comments
```

#### 1.5 Database Storage
```python
# scraper/storage.py
import sqlite3
import json
from pathlib import Path
from .models import LiftPost

class Storage:
    def __init__(self, db_path: str = "data/metadata.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                lift_type TEXT NOT NULL,
                title TEXT,
                video_url TEXT,
                video_path TEXT,
                created_utc TIMESTAMP,
                author TEXT,
                post_score INTEGER,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                post_id TEXT,
                body TEXT,
                score INTEGER,
                author TEXT,
                created_utc TIMESTAMP,
                FOREIGN KEY (post_id) REFERENCES posts(id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_lift_type ON posts(lift_type)
        """)

        conn.commit()
        conn.close()

    def save_post(self, post: LiftPost):
        """Save post and comments to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Insert post
        cursor.execute("""
            INSERT OR REPLACE INTO posts
            (id, lift_type, title, video_url, video_path, created_utc, author, post_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            post.id,
            post.lift_type,
            post.title,
            str(post.video_url),
            post.video_path,
            post.created_utc,
            post.author,
            post.post_score
        ))

        # Insert comments
        for comment in post.comments:
            cursor.execute("""
                INSERT OR REPLACE INTO comments
                (id, post_id, body, score, author, created_utc)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                comment.id,
                post.id,
                comment.body,
                comment.score,
                comment.author,
                comment.created_utc
            ))

        conn.commit()
        conn.close()

    def post_exists(self, post_id: str) -> bool:
        """Check if post already scraped"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posts WHERE id = ?", (post_id,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
```

#### 1.6 CLI Interface
```python
# scraper/cli.py
import click
from .reddit_scraper import RedditScraper
from .config import LIFT_REGISTRY
import os

@click.group()
def cli():
    """AutoCoach data collection CLI"""
    pass

@cli.command()
@click.option('--lift', type=click.Choice(list(LIFT_REGISTRY.keys())), help='Lift type to scrape')
@click.option('--limit', default=100, help='Max posts to scrape')
@click.option('--all', is_flag=True, help='Scrape all lift types')
def scrape(lift, limit, all):
    """Scrape Reddit for form check videos"""

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        click.echo("Error: Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars")
        return

    scraper = RedditScraper(client_id, client_secret)

    lifts_to_scrape = list(LIFT_REGISTRY.keys()) if all else [lift]

    for lift_type in lifts_to_scrape:
        click.echo(f"Scraping {lift_type}...")
        posts = scraper.scrape_lift(lift_type, limit=limit)
        click.echo(f"  Found {len(posts)} new posts with comments")

        # Download videos
        for post in posts:
            click.echo(f"  Downloading {post.id}...")
            scraper.download_video(post)

if __name__ == '__main__':
    cli()
```

**Success Criteria:**
- ✅ Scraper collects videos + comments + scores
- ✅ Data stored in structured database
- ✅ Incremental scraping (no duplicates)
- ✅ At least 50 high-quality posts per lift type
- ✅ CLI tool works end-to-end

**Testing:**
```bash
# Test scraping
python -m scraper.cli scrape --lift squat --limit 10

# Verify database
sqlite3 data/metadata.db "SELECT COUNT(*) FROM posts;"
sqlite3 data/metadata.db "SELECT COUNT(*) FROM comments;"
```

---

### Phase 2: Pose Processing Pipeline (Weeks 2-3)
**Goal:** Extract pose landmarks, normalize to a canonical representation, and derive biomechanical features from videos

**Module name:** `pose` (renamed from `transformer` — avoids ambiguity with ML transformer architecture)

#### Design Principle: Normalizer Interface

The normalization step sits between raw MediaPipe output and feature extraction. It is abstracted behind a Protocol so the implementation can be swapped in v2 without touching downstream code:

```python
# pose/normalizer.py
from typing import Protocol
from .models import PoseSequence, NormalizedPoseSequence

class PoseNormalizer(Protocol):
    def normalize(self, raw: PoseSequence) -> NormalizedPoseSequence: ...
```

#### Normalization: v1 vs v2

**v1 (Rule-based, implemented in Phase 2)**

Assumptions and approach:
- Assume side-view footage (the r/formcheck community norm — posts without side-view rarely receive useful feedback and can be filtered at scrape time by detecting left/right landmark symmetry)
- Raw MediaPipe `(x, y, z)` coordinates are viewport-relative and vary with camera distance and body size — do not store them directly as features
- Instead, derive **joint angles** (hip, knee, ankle flexion; back inclination from vertical) — these are scale-invariant and meaningful for form analysis
- Apply **phase-based temporal normalization**: detect key lift events (descent start → depth/parallel → ascent → lockout) using hip height relative to knee as a proxy, then resample each phase independently to a fixed frame count. This ensures the bottom position — the most diagnostically important moment — aligns across lifts of different speeds.
- Flag and skip videos where landmark visibility is consistently below threshold (occluded, wrong angle)

```
pose/
├── __init__.py
├── extractor.py               # MediaPipe wrapper → raw PoseSequence
├── normalizer.py              # PoseNormalizer Protocol + RuleBasedNormalizer
├── phases.py                  # Phase detection (descent/depth/ascent/lockout)
├── biomechanics.py            # Joint angle extraction from normalized sequence
├── models.py                  # Frame, PoseSequence, NormalizedPoseSequence
└── filters.py                 # View quality filter (rejects front-on footage)
```

**v2 (ML-based, planned for post-v1)**

Replace `RuleBasedNormalizer` with a 3D pose lifting model:
- **MotionBERT** (2023, transformer-based) or **VideoPose3D** (dilated temporal convolutions, simpler) — both take sequences of 2D landmarks and output 3D joint positions
- Once 3D positions are available, reproject to a canonical sagittal view via rotation matrix — fully camera-angle-agnostic
- Both models have pretrained weights trained on Human3.6M + AMASS mocap data; powerlifting generalizes reasonably given the constrained movement patterns
- Fine-tuning would require multi-camera powerlifting footage with ground-truth 3D (mocap lab) — not feasible in v1, revisit if retrieval quality proves insufficient
- The `PoseNormalizer` Protocol means this is a drop-in replacement with no changes to `biomechanics.py`, `rag/`, or anything downstream

**Deliverables:**

#### 2.1 Module Structure
```
pose/
├── __init__.py
├── extractor.py               # MediaPipe wrapper
├── normalizer.py              # PoseNormalizer Protocol + RuleBasedNormalizer (v1)
├── phases.py                  # Phase detection
├── biomechanics.py            # Feature extraction from normalized sequence
├── models.py                  # Pose data models
└── filters.py                 # View quality checks
```

#### 2.2 Pose Extraction
```python
# pose/extractor.py
import mediapipe as mp
import cv2
import numpy as np
from typing import List, Optional
from .models import Frame, PoseSequence

class PoseExtractor:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def extract_from_video(
        self,
        video_path: str,
        sample_rate: int = 2  # Process every Nth frame
    ) -> Optional[PoseSequence]:
        """Extract pose landmarks from video"""

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None

        frames = []
        frame_idx = 0

        while cap.isOpened():
            ret, image = cap.read()
            if not ret:
                break

            # Sample frames
            if frame_idx % sample_rate != 0:
                frame_idx += 1
                continue

            # Process with MediaPipe
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = self.pose.process(image_rgb)

            if results.pose_landmarks:
                landmarks = self._landmarks_to_array(results.pose_landmarks)
                frames.append(Frame(
                    index=frame_idx,
                    landmarks=landmarks,
                    timestamp=cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                ))

            frame_idx += 1

        cap.release()

        if not frames:
            return None

        return PoseSequence(
            video_id=Path(video_path).stem,
            frames=frames
        )

    def _landmarks_to_array(self, landmarks) -> np.ndarray:
        """Convert MediaPipe landmarks to NumPy array"""
        return np.array([
            [lm.x, lm.y, lm.z, lm.visibility]
            for lm in landmarks.landmark
        ])
```

#### 2.3 Biomechanical Features
```python
# pose/biomechanics.py
import numpy as np
from typing import Dict
from .models import PoseSequence

class BiomechanicsAnalyzer:
    # MediaPipe landmark indices
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28

    def analyze(self, pose_sequence: PoseSequence) -> Dict:
        """Extract biomechanical features"""

        features = {
            "hip_angles": self._calculate_hip_angles(pose_sequence),
            "knee_angles": self._calculate_knee_angles(pose_sequence),
            "back_angles": self._calculate_back_angles(pose_sequence),
            "depth": self._calculate_depth(pose_sequence),
            "bar_path": self._calculate_bar_path(pose_sequence),
            "tempo": self._calculate_tempo(pose_sequence),
        }

        return features

    def _calculate_angle(self, p1, p2, p3) -> float:
        """Calculate angle between three points"""
        v1 = p1 - p2
        v2 = p3 - p2
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))
        angle = np.arccos(np.clip(cos_angle, -1.0, 1.0))
        return np.degrees(angle)

    def _calculate_hip_angles(self, pose_sequence: PoseSequence) -> List[float]:
        """Calculate hip angle for each frame"""
        angles = []
        for frame in pose_sequence.frames:
            shoulder = frame.landmarks[self.LEFT_SHOULDER][:3]
            hip = frame.landmarks[self.LEFT_HIP][:3]
            knee = frame.landmarks[self.LEFT_KNEE][:3]
            angle = self._calculate_angle(shoulder, hip, knee)
            angles.append(angle)
        return angles
```

#### 2.4 Process All Scraped Videos
```python
# pose/cli.py
import click
from pathlib import Path
from .extractor import PoseExtractor
from .biomechanics import BiomechanicsAnalyzer
import json

@click.command()
@click.argument('video_dir', type=click.Path(exists=True))
@click.argument('output_dir', type=click.Path())
def process(video_dir, output_dir):
    """Process all videos in directory"""

    extractor = PoseExtractor()
    analyzer = BiomechanicsAnalyzer()

    video_files = list(Path(video_dir).rglob("*.mp4"))
    click.echo(f"Processing {len(video_files)} videos...")

    for video_path in video_files:
        click.echo(f"  {video_path.name}")

        # Extract poses
        pose_sequence = extractor.extract_from_video(str(video_path))
        if not pose_sequence:
            click.echo("    Failed to extract poses")
            continue

        # Analyze biomechanics
        features = analyzer.analyze(pose_sequence)

        # Save results
        output_path = Path(output_dir) / f"{video_path.stem}_pose.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump({
                "video_id": pose_sequence.video_id,
                "num_frames": len(pose_sequence.frames),
                "features": features
            }, f, indent=2)

        click.echo("    ✓ Done")
```

**Success Criteria:**
- ✅ Extract poses from all scraped videos
- ✅ Calculate biomechanical features per lift type
- ✅ Store pose data in structured format
- ✅ <2s processing time per video

---

### Phase 3: RAG System (Weeks 3-4)
**Goal:** Set up vector database and retrieval system

**Deliverables:**

#### 3.1 Vector DB Setup
```python
# rag/embeddings.py
from sentence_transformers import SentenceTransformer
import numpy as np

class EmbeddingGenerator:
    def __init__(self):
        # Lightweight, free, local model
        self.text_model = SentenceTransformer('all-MiniLM-L6-v2')

    def embed_comment(self, text: str) -> np.ndarray:
        """Generate text embedding"""
        return self.text_model.encode(text)

    def embed_pose(self, pose_features: Dict) -> np.ndarray:
        """Generate pose embedding (simple approach)"""
        # Flatten features into vector
        feature_vector = np.concatenate([
            pose_features["hip_angles"],
            pose_features["knee_angles"],
            # ... other features
        ])

        # Reduce dimensionality (PCA or average)
        return self._reduce_dim(feature_vector, target_dim=512)
```

#### 3.2 Qdrant Integration
```python
# rag/vector_store.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

class LiftVectorStore:
    def __init__(self):
        self.client = QdrantClient(":memory:")  # Local for dev
        self._init_collection()

    def _init_collection(self):
        """Create Qdrant collection"""
        self.client.create_collection(
            collection_name="lift_coaching",
            vectors_config={
                "pose": VectorParams(size=512, distance=Distance.COSINE),
                "comment": VectorParams(size=384, distance=Distance.COSINE)
            }
        )

    def index_lift(
        self,
        video_id: str,
        lift_type: str,
        pose_embedding: np.ndarray,
        comments: List[Dict],
        comment_embeddings: List[np.ndarray],
        pose_features: Dict
    ):
        """Add lift to vector store"""

        self.client.upsert(
            collection_name="lift_coaching",
            points=[{
                "id": video_id,
                "vector": {
                    "pose": pose_embedding.tolist(),
                    "comment": np.mean(comment_embeddings, axis=0).tolist()
                },
                "payload": {
                    "lift_type": lift_type,
                    "comments": comments,
                    "pose_features": pose_features
                }
            }]
        )

    def search_similar(
        self,
        query_pose_embedding: np.ndarray,
        lift_type: str,
        limit: int = 5
    ) -> List[Dict]:
        """Find similar lifts"""

        results = self.client.search(
            collection_name="lift_coaching",
            query_vector=("pose", query_pose_embedding.tolist()),
            query_filter={
                "must": [
                    {"key": "lift_type", "match": {"value": lift_type}}
                ]
            },
            limit=limit
        )

        return [hit.payload for hit in results]
```

**Success Criteria:**
- ✅ All scraped videos indexed in Qdrant
- ✅ Similarity search returns relevant results (<50ms)
- ✅ Hybrid search (pose + comment quality) works

---

### Phase 4: LLM Integration (Week 4-5)
**Goal:** Generate coaching feedback using litellm

**Deliverables:**

#### 4.1 litellm Setup
```python
# coaching/llm_coach.py
import litellm
from typing import List, Dict
import os

litellm.api_key = os.getenv("ANTHROPIC_API_KEY")

class CoachingGenerator:
    PROVIDER_CHAIN = [
        "claude-3-haiku-20240307",
        "gpt-4o-mini",
        "gemini/gemini-1.5-flash"
    ]

    async def generate(
        self,
        user_features: Dict,
        similar_lifts: List[Dict],
        safety_issues: List[str]
    ) -> str:
        """Generate coaching feedback with fallback"""

        prompt = self._construct_prompt(user_features, similar_lifts, safety_issues)

        for model in self.PROVIDER_CHAIN:
            try:
                response = await litellm.acompletion(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an expert powerlifting coach."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=300,
                    temperature=0.7
                )
                return response.choices[0].message.content
            except Exception as e:
                print(f"Provider {model} failed: {e}")
                continue

        return "Unable to generate coaching feedback at this time."

    def _construct_prompt(self, user_features, similar_lifts, safety_issues):
        """Build coaching prompt"""
        # ... (as in architecture doc)
```

#### 4.2 Caching Layer
```python
# coaching/cache.py
import redis
import hashlib
import json

class CoachingCache:
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379, db=0)
        self.ttl = 30 * 24 * 3600  # 30 days

    def get(self, features: Dict) -> Optional[str]:
        """Get cached coaching"""
        key = self._cache_key(features)
        cached = self.redis.get(key)
        return cached.decode() if cached else None

    def set(self, features: Dict, coaching: str):
        """Cache coaching response"""
        key = self._cache_key(features)
        self.redis.setex(key, self.ttl, coaching)

    def _cache_key(self, features: Dict) -> str:
        """Generate cache key from features"""
        rounded = {k: round(v, 0) if isinstance(v, float) else v
                   for k, v in features.items()}
        canonical = json.dumps(rounded, sort_keys=True)
        return f"coaching:{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"
```

**Success Criteria:**
- ✅ LLM generates relevant coaching
- ✅ Fallback works if primary provider fails
- ✅ Cache hit rate >30%
- ✅ Cost per analysis <$0.01

---

### Phase 5: API & Frontend (Weeks 5-7)
**Goal:** Build user-facing API and simple web UI

**Deliverables:**

#### 5.1 FastAPI Backend
```python
# api/main.py
from fastapi import FastAPI, UploadFile, File
from celery import Celery
import uuid

app = FastAPI(title="AutoCoach API")
celery = Celery('autocoach', broker='redis://localhost:6379')

@app.post("/api/v1/analyze")
async def analyze_video(
    video: UploadFile = File(...),
    lift_type: str = "squat"
):
    """Upload video for analysis"""

    video_id = str(uuid.uuid4())
    video_path = f"/tmp/uploads/{video_id}.mp4"

    # Save uploaded video
    with open(video_path, "wb") as f:
        content = await video.read()
        f.write(content)

    # Queue processing
    task = celery.send_task('process_video', args=[video_id, video_path, lift_type])

    return {
        "video_id": video_id,
        "task_id": task.id,
        "status": "queued"
    }
```

#### 5.2 Celery Worker (Orchestrates Everything)
```python
# worker/tasks.py
from celery import Celery
from transformer.pose_extractor import PoseExtractor
from rag.vector_store import LiftVectorStore
from coaching.llm_coach import CoachingGenerator

celery = Celery('autocoach', broker='redis://localhost:6379')

@celery.task(bind=True)
def process_video(self, video_id, video_path, lift_type):
    """Process video end-to-end"""

    # 1. Extract pose
    extractor = PoseExtractor()
    pose_sequence = extractor.extract_from_video(video_path)

    # 2. Analyze biomechanics
    analyzer = BiomechanicsAnalyzer()
    features = analyzer.analyze(pose_sequence)

    # 3. Check safety
    critic = LiftCritic(lift_type)
    issues = critic.check(pose_sequence)

    # 4. Search similar lifts
    vector_store = LiftVectorStore()
    similar = vector_store.search_similar(features["embedding"], lift_type)

    # 5. Generate coaching
    coach = CoachingGenerator()
    feedback = await coach.generate(features, similar, issues)

    # 6. Save results
    save_results(video_id, feedback, features, issues)

    return {"status": "complete", "video_id": video_id}
```

#### 5.3 Simple Web UI (Next.js)
```tsx
// app/page.tsx
'use client'

import { useState } from 'react'

export default function Home() {
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<any>(null)

  const handleSubmit = async () => {
    const formData = new FormData()
    formData.append('video', file!)
    formData.append('lift_type', 'squat')

    const res = await fetch('/api/analyze', {
      method: 'POST',
      body: formData
    })

    const data = await res.json()
    // Poll for results...
    const results = await pollResults(data.video_id)
    setResult(results)
  }

  return (
    <div>
      <h1>AutoCoach</h1>
      <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
      <button onClick={handleSubmit}>Analyze Form</button>

      {result && (
        <div>
          <h2>Coaching Feedback</h2>
          <p>{result.coaching}</p>
          <video src={result.overlay_url} controls />
        </div>
      )}
    </div>
  )
}
```

**Success Criteria:**
- ✅ End-to-end analysis works via API
- ✅ Web UI for video upload
- ✅ Results display in <5s
- ✅ Basic error handling

---

## Timeline Summary

| Phase | Duration | Key Milestone |
|-------|----------|---------------|
| 1: Data Collection | 1-2 weeks | 150+ posts with comments |
| 2: Pose Processing | 1 week | All videos processed |
| 3: RAG System | 1 week | Vector search working |
| 4: LLM Integration | 1 week | Coaching generation working |
| 5: API & Frontend | 2-3 weeks | Demo-ready web app |
| **Total** | **6-8 weeks** | **Working prototype** |

---

## Success Metrics

**Phase 1:**
- ✅ 50+ high-quality posts per lift type
- ✅ Average 5+ comments per post
- ✅ Scraper runs incrementally

**Phase 2:**
- ✅ 90%+ videos successfully processed
- ✅ <2s processing time per video
- ✅ Biomechanical features extracted

**Phase 3:**
- ✅ All videos indexed in Qdrant
- ✅ Similarity search <50ms
- ✅ Retrieval quality validated

**Phase 4:**
- ✅ LLM generates coherent feedback
- ✅ Cache hit rate >30%
- ✅ Cost <$0.01 per analysis

**Phase 5:**
- ✅ End-to-end analysis <5s
- ✅ Web UI functional
- ✅ Ready for user testing

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Reddit API limits | High | Rate limiting, caching, backup sources |
| MediaPipe accuracy | Medium | Manual validation, MMPose fallback |
| LLM costs too high | High | Aggressive caching, skip for good form |
| Poor retrieval quality | Medium | Fine-tune embeddings, add filters |
| Videos too large | Low | Preprocessing compression |

---

## Next Steps After Phase 5

1. **User Testing** - Get feedback from real lifters
2. **Model Tuning** - Improve pose embeddings based on retrieval quality
3. **Mobile App** - React Native for on-the-go analysis
4. **Social Features** - Share analyses, compare with others
5. **Additional Lifts** - Overhead press, rows, etc.

---

## Questions to Answer During Development

**Phase 1:**
- What's the optimal min_comment threshold? (currently 3)
- Should we filter by upvotes on posts too?

**Phase 2:**
- Is 15fps (sample_rate=2) sufficient? Test at 30fps too
- Which biomechanical features are most predictive?

**Phase 3:**
- How to weight pose vs comment similarity?
- Optimal embedding dimension (512? 256?)

**Phase 4:**
- Which LLM provider gives best quality/cost?
- How aggressive should caching be?

**Phase 5:**
- What's the minimum viable UI?
- Should we support multiple lifts per video?

---

**Ready to start? Let's build Phase 1!** 🚀
