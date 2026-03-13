# Performance Optimization Strategy

**Last Updated:** 2026-03-09
**Objective:** Minimize cost per analysis while maintaining <3s processing time

---

## Performance Goals

| Metric | Target | Stretch |
|--------|--------|---------|
| Processing Time (per video) | <3s | <1s |
| Cost per Analysis | <$0.02 | <$0.01 |
| Throughput (per worker) | 1200/hour | 3600/hour |
| 99th Percentile Latency | <5s | <2s |

---

## Cost Breakdown Analysis

### Where Time & Money Are Spent

```
Per-Video Cost Breakdown:
├─ Video I/O & Decoding        ~1.0s  (40%)  $0.000  [Bottleneck: Codec]
├─ Pose Estimation             ~1.2s  (48%)  $0.000  [Bottleneck: MediaPipe CPU]
├─ Feature Extraction          ~0.1s  (4%)   $0.000  [Python NumPy]
├─ Vector Search               ~0.05s (2%)   $0.000  [Qdrant is fast]
├─ LLM API Call                ~0.3s  (12%)  $0.015  [Network + tokens]
└─ Overlay Generation          ~0.1s  (4%)   $0.000  [OpenCV]
────────────────────────────────────────────────────
Total (baseline):              ~2.75s        ~$0.015
```

**Key Insight:** LLM calls are 100% of cost but only 12% of time. Pose estimation is 48% of time but $0.

---

## Optimization Strategy

### 1. Video Processing (40% of time)

**Problem:** Video decoding is slow, especially for high-res videos from phones.

**Solutions:**

#### A. Preprocessing (Client or Server)
```bash
# Compress and normalize videos on upload
ffmpeg -i input.mp4 \
  -vf "scale=720:-1" \      # Downscale to 720p
  -c:v libx264 \            # H.264 codec
  -preset fast \            # Fast encoding
  -crf 28 \                 # Aggressive compression
  -an \                     # Remove audio
  output.mp4

# Expected: 50MB → 5MB, decoding 2x faster
```

**Impact:** 40-50% reduction in I/O time
**Trade-off:** Slight quality loss (acceptable for pose estimation)

#### B. Use Hardware Acceleration
```python
# Use GPU-accelerated decoding (if available)
cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY)
```

**Impact:** 2-3x faster on GPU-enabled instances
**Cost:** $0.10-0.20/hour for GPU instance vs $0.05 for CPU

#### C. Parallel Frame Extraction
```python
from concurrent.futures import ThreadPoolExecutor

def extract_frames_parallel(video_path, sample_rate=2):
    """Extract every Nth frame in parallel"""
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Only process every 2nd frame (30fps → 15fps is enough)
    frame_indices = range(0, total_frames, sample_rate)

    with ThreadPoolExecutor(max_workers=4) as executor:
        frames = list(executor.map(
            lambda idx: read_frame(cap, idx),
            frame_indices
        ))

    return frames
```

**Impact:** 50% fewer frames to process
**Trade-off:** None for form analysis (15fps is sufficient)

---

### 2. Pose Estimation (48% of time)

**Problem:** MediaPipe is CPU-bound, processes frames sequentially.

**Solutions:**

#### A. Multiprocessing (Bypass GIL)
```python
from multiprocessing import Pool

def process_video_parallel(video_path):
    # Split video into chunks
    frame_chunks = split_into_chunks(extract_frames(video_path), chunk_size=30)

    # Process each chunk in parallel
    with Pool(processes=4) as pool:
        results = pool.map(process_chunk_with_mediapipe, frame_chunks)

    return concatenate_results(results)

def process_chunk_with_mediapipe(frames):
    """Each process has its own MediaPipe instance"""
    pose = mp_pose.Pose()
    landmarks = [pose.process(frame) for frame in frames]
    pose.close()
    return landmarks
```

**Impact:** 3-4x speedup on 4-core CPU
**Cost:** Minimal (same instance, better utilization)

#### B. Batch Processing
```python
# Process multiple videos in one worker lifecycle
# Amortize MediaPipe initialization cost

def batch_process(video_paths: List[str]):
    pose = mp_pose.Pose()  # Initialize once
    results = []

    for video_path in video_paths:
        frames = extract_frames(video_path)
        landmarks = [pose.process(f) for f in frames]
        results.append(landmarks)

    pose.close()
    return results
```

**Impact:** 10-15% faster by reusing model instance

#### C. Consider MMPose (if MediaPipe is too slow)
```python
# MMPose has faster inference with similar accuracy
from mmpose.apis import init_pose_model, process_mmdet_results

model = init_pose_model(
    'configs/body/2d_kpt_sview_rgb_img/topdown_heatmap/coco/hrnet_w48_coco_256x192.py',
    'checkpoints/hrnet_w48.pth',
    device='cuda:0'  # GPU required
)
```

**Impact:** 2-3x faster on GPU
**Cost:** Requires GPU instance ($0.10-0.20/hour)

---

### 3. LLM Calls (100% of cost)

**Problem:** Every analysis costs $0.015 in LLM tokens.

**Solutions:**

#### A. Semantic Caching (HIGH IMPACT)
```python
import hashlib
from redis import Redis

redis_client = Redis()

def semantic_cache_key(pose_features: Dict) -> str:
    """Round features to reduce cache misses from tiny variations"""

    rounded = {
        "hip_angle": round(pose_features["hip_angle"], 0),  # Round to degree
        "knee_tracking": pose_features["knee_tracking"],
        "depth": pose_features["depth"],
        # ... other features
    }

    canonical = json.dumps(rounded, sort_keys=True)
    return f"coaching:{hashlib.sha256(canonical.encode()).hexdigest()[:12]}"

async def get_coaching_cached(pose_features, similar_lifts, issues):
    cache_key = semantic_cache_key(pose_features)

    # Check cache
    cached = redis_client.get(cache_key)
    if cached:
        logger.info("Cache hit!")
        return json.loads(cached)

    # Generate new
    coaching = await generate_coaching(pose_features, similar_lifts, issues)

    # Cache for 30 days
    redis_client.setex(cache_key, 30*24*3600, json.dumps(coaching))

    return coaching
```

**Expected Cache Hit Rate:** 30-50% (similar forms are common)
**Impact:** 30-50% reduction in LLM costs
**New Cost:** $0.015 → $0.008 per analysis

#### B. Skip LLM for "Good" Form
```python
def needs_llm_coaching(safety_issues: List, pose_features: Dict) -> bool:
    """Only call LLM if there are issues or user explicitly requests"""

    # No safety issues and metrics are in acceptable ranges
    if not safety_issues and all_metrics_good(pose_features):
        return False  # Return canned "looks good" message

    return True  # User has form issues, generate coaching

# Estimated: 20-30% of lifts are "good enough" → skip LLM
```

**Impact:** 20-30% reduction in LLM calls
**New Cost:** $0.008 → $0.006 per analysis

#### C. Use Cheaper Models
```python
# Current: Claude Haiku ($0.25/$1.25 per M tokens)
# Alternative: GPT-4o-mini ($0.15/$0.60 per M tokens)

# For 500 token output:
# Haiku: ~$0.015
# GPT-4o-mini: ~$0.010
# Gemini Flash: ~$0.007
```

**Recommendation:** Start with Haiku (best quality), switch to GPT-4o-mini if cost is issue.

#### D. Prompt Optimization
```python
# Reduce output tokens by being prescriptive

OPTIMIZED_PROMPT = """
Analyze this {lift_type} and provide exactly 3 bullet points:
1. Most critical form issue (if any)
2. One specific cue to fix it
3. One drill to practice

Be concise. Max 100 words total.

USER METRICS: {metrics}
SAFETY ISSUES: {issues}
SIMILAR LIFTS: {similar_comments}
"""

# Typical output: 80-120 tokens vs 200-300 tokens
# Cost reduction: 50-60%
```

**Impact:** 50% reduction in output tokens
**New Cost:** $0.006 → $0.003 per analysis

#### E. Batch LLM Calls (for async processing)
```python
# If processing multiple videos, batch them
async def batch_generate_coaching(requests: List[Dict]):
    """Call LLM once with multiple requests"""

    batched_prompt = "\n\n---\n\n".join([
        f"VIDEO {i}:\n{construct_prompt(req)}"
        for i, req in enumerate(requests)
    ])

    response = await litellm.acompletion(
        model="claude-3-haiku-20240307",
        messages=[{"role": "user", "content": batched_prompt}]
    )

    # Parse multiple responses
    return parse_batched_response(response.choices[0].message.content)
```

**Impact:** 10-15% cost reduction (shared prompt overhead)

---

### 4. Combined Optimization Impact

**Baseline (no optimization):**
- Time: 2.75s
- Cost: $0.015

**After all optimizations:**
```
├─ Video I/O: 1.0s → 0.5s (preprocessing + sampling)
├─ Pose: 1.2s → 0.4s (multiprocessing + sampling)
├─ Features: 0.1s → 0.1s (no change)
├─ Search: 0.05s → 0.05s (no change)
├─ LLM: $0.015 → $0.003 (caching + skipping + prompt optimization)
├─ Overlay: 0.1s → 0.1s (no change)
────────────────────────────────────────────────
Total: 1.15s, $0.003
```

**Improvement:**
- ✅ Time: 2.75s → 1.15s (58% faster)
- ✅ Cost: $0.015 → $0.003 (80% cheaper)
- ✅ Throughput: 1300/hour → 3100/hour (2.4x)

---

## Performance Testing Plan

### 1. Benchmark Suite

```python
# tests/performance/benchmark.py

import time
from statistics import mean, stdev

def benchmark_component(func, iterations=100):
    """Benchmark a single component"""
    times = []

    for _ in range(iterations):
        start = time.time()
        func()
        times.append(time.time() - start)

    return {
        "mean": mean(times),
        "stdev": stdev(times),
        "p95": sorted(times)[int(0.95 * len(times))],
        "p99": sorted(times)[int(0.99 * len(times))]
    }

# Run benchmarks
results = {
    "video_decode": benchmark_component(lambda: extract_frames(TEST_VIDEO)),
    "pose_estimation": benchmark_component(lambda: estimate_pose(TEST_FRAMES)),
    "feature_extraction": benchmark_component(lambda: extract_features(TEST_POSE)),
    "vector_search": benchmark_component(lambda: search_similar(TEST_EMBEDDING)),
    "llm_call": benchmark_component(lambda: generate_coaching(TEST_DATA)),
}

print_performance_report(results)
```

### 2. Load Testing

```python
# tests/performance/load_test.py

from locust import HttpUser, task, between

class AutoCoachUser(HttpUser):
    wait_time = between(1, 5)

    @task
    def upload_video(self):
        with open("test_video.mp4", "rb") as f:
            self.client.post("/api/v1/analyze", files={"video": f})

    @task(3)  # 3x more status checks than uploads
    def check_status(self):
        self.client.get(f"/api/v1/status/{self.task_id}")

# Run: locust -f load_test.py --host http://localhost:8000
```

### 3. Cost Tracking

```python
# app/monitoring/cost_tracker.py

from prometheus_client import Counter, Histogram

llm_cost_counter = Counter(
    'llm_cost_total',
    'Total LLM API cost in USD',
    ['model', 'cache_status']
)

llm_latency_histogram = Histogram(
    'llm_latency_seconds',
    'LLM API call latency',
    ['model']
)

def track_llm_call(model, cost, latency, cached):
    llm_cost_counter.labels(
        model=model,
        cache_status='hit' if cached else 'miss'
    ).inc(cost)

    llm_latency_histogram.labels(model=model).observe(latency)
```

---

## Python-Specific Optimizations

### 1. Use NumPy for Vectorization

**Bad (Python loops):**
```python
def calculate_angles(landmarks):
    angles = []
    for i in range(len(landmarks) - 2):
        p1, p2, p3 = landmarks[i], landmarks[i+1], landmarks[i+2]
        angle = calculate_angle(p1, p2, p3)  # Python function
        angles.append(angle)
    return angles
```

**Good (NumPy vectorization):**
```python
def calculate_angles_vectorized(landmarks):
    # Convert to NumPy array
    points = np.array([[lm.x, lm.y, lm.z] for lm in landmarks])

    # Vectorized angle calculation
    v1 = points[:-2] - points[1:-1]
    v2 = points[2:] - points[1:-1]

    angles = np.arccos(
        np.sum(v1 * v2, axis=1) /
        (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1))
    )

    return angles
```

**Impact:** 10-50x faster for large arrays

### 2. Use `__slots__` for Data Classes

```python
# Instead of regular class
class Landmark:
    __slots__ = ['x', 'y', 'z', 'visibility']  # Use slots to reduce memory

    def __init__(self, x, y, z, visibility):
        self.x = x
        self.y = y
        self.z = z
        self.visibility = visibility
```

**Impact:** 40-50% memory reduction, 10% faster attribute access

### 3. Use Cython for Hot Paths (if needed)

```cython
# biomechanics.pyx

import numpy as np
cimport numpy as np

def calculate_joint_angles(np.ndarray[np.float64_t, ndim=2] landmarks):
    """Cython-optimized angle calculation"""
    cdef int i
    cdef double angle
    cdef np.ndarray[np.float64_t, ndim=1] angles = np.zeros(len(landmarks) - 2)

    for i in range(len(landmarks) - 2):
        angles[i] = compute_angle(landmarks[i], landmarks[i+1], landmarks[i+2])

    return angles
```

**Impact:** 2-10x faster than pure Python
**Trade-off:** More complex build process

---

## When to Consider Alternative Languages

**Stay with Python if:**
- ✅ Total processing time <3s (current: ~1.15s optimized)
- ✅ Cost per analysis <$0.02 (current: ~$0.003)
- ✅ Throughput <10,000 videos/day
- ✅ Development speed matters

**Consider Rust/Go if:**
- ❌ Processing time >5s after Python optimization
- ❌ Need real-time analysis (<500ms)
- ❌ Processing >100,000 videos/day
- ❌ Cost >$1000/month on compute

**For this project: Python is the right choice.**

---

## Production Performance SLAs

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| API Latency (upload) | <200ms | >500ms |
| Processing Time | <3s | >5s |
| Error Rate | <1% | >5% |
| LLM Cost per 1000 analyses | <$3 | >$20 |
| Cache Hit Rate | >30% | <20% |
| Queue Depth | <50 | >200 |

---

## Continuous Optimization

1. **Weekly:** Review cost metrics, adjust caching strategy
2. **Monthly:** Analyze slow traces, optimize bottlenecks
3. **Quarterly:** Re-benchmark, consider new models/techniques

---

## References

- Python Performance Tips: https://wiki.python.org/moin/PythonSpeed
- NumPy Optimization: https://numpy.org/doc/stable/user/performance.html
- MediaPipe Performance: https://google.github.io/mediapipe/getting_started/troubleshooting.html
