# Coaching Roadmap — CEO Plan Review

**Date:** 2026-03-17
**Mode:** Selective Expansion
**Branch:** main
**Status:** CLEAR (0 unresolved decisions, 0 critical gaps)

---

## Scope

Full remaining roadmap: Phases 4-5 (LLM coaching, API/frontend) plus P2/P3 enhancements.

### Accepted Expansions (cherry-picked from SELECTIVE EXPANSION)

1. **Instant rule-based tips** — API returns scoring-derived cues (<100ms) while LLM generates deeper feedback in the background
2. **Lift type auto-detection** — heuristic classifier on BiomechanicalFeatures, fallback to user selection if confidence < threshold
3. **Structured logging + trace IDs** — `structlog` with `video_id` as trace key across all new modules

### Deferred

- Shareable form card image (depends on overlay/)
- Coaching tone selector (system prompt variants)
- Quick tips cue database (Reddit comment mining)
- Progress sparkline (frontend, depends on history API)

---

## System Architecture

```
                            ┌─────────────────────┐
                            │     Web UI (Next.js) │
                            └──────────┬──────────┘
                                       │ POST /api/v1/analyze
                                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI (api/)                             │
│  POST /analyze  GET /status/{id}  GET /results/{id}  GET /history│
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ Instant tips      │    │ Full results     │                   │
│  │ (sync, <100ms)    │    │ (poll worker)    │                   │
│  │ scoring/ → tips   │    │ DB + blob/       │                   │
│  └──────────────────┘    └──────────────────┘                   │
└──────────┬───────────────────────┬───────────────────────────────┘
           │                       │ Celery task
           │                       ▼
           │         ┌─────────────────────────────┐
           │         │      Worker (worker/)         │
           │         │                               │
           │         │  1. (features already computed)│
           │         │  2. rag/store → similar lifts  │
           │         │  3. coaching/ → LLM synthesis   │
           │         │  4. overlay/ → keyframe images  │
           │         │  5. blob/ ← store keyframes     │
           │         │  6. db/ ← store CoachingReport  │
           │         │                               │
           │         └──┬────────┬─────────┬────────┘
           │            │        │         │
           ▼            ▼        ▼         ▼
     ┌──────────┐ ┌─────────┐ ┌──────┐ ┌────────┐
     │ Redis    │ │PostgreSQL│ │Qdrant│ │ blob/  │
     │ (broker) │ │(metadata)│ │(vecs)│ │(files) │
     └──────────┘ └─────────┘ └──────┘ └────────┘
```

### Key Architectural Decision: Pipeline Split

The API runs pose processing + scoring **synchronously** (in a thread pool via
`run_in_executor()`), returning instant rule-based tips in the HTTP response.
It then queues a Celery task with the serialized `BiomechanicalFeatures` for
the worker to continue with RAG + LLM + overlay.

This avoids double-processing (pose pipeline is CPU-expensive, ~2-3s) and
gives users immediate feedback while the LLM generates deeper coaching.

```
API process (sync, 2-3s):
  blob/ → pose/pipeline → scoring/ → instant tips response
  + enqueue Celery task(features_json, video_key)

Worker process (async, 3-5s):
  deserialize features → rag/ → coaching/ → overlay/ → db/ + blob/
```

### Dependency Graph

```
api/ ──→ worker/ (via Celery)
api/ ──→ scoring/ (sync, for instant tips)
api/ ──→ db/ (results retrieval)
api/ ──→ blob/ (keyframe image URLs)
worker/ ──→ rag/ ──→ coaching/ ──→ overlay/ ──→ db/
coaching/ ──→ litellm (external)
scoring/ ──→ pose/models (BiomechanicalFeatures)
overlay/ ──→ pose/models + scoring/ + cv2
```

### Result Storage

- **PostgreSQL:** Analysis metadata, coaching text, form scores, user history
- **blob/:** Keyframe images (annotated PNGs), uploaded videos
- Split chosen for clean separation: schema evolution + relational queries vs large-object streaming

### Scaling Bottlenecks (in order)

1. **Celery workers** — CPU-bound MediaPipe. Horizontal scaling works.
2. **LLM provider rate limits** — fallback chain mitigates but doesn't eliminate.
3. **blob/ storage** — local filesystem for dev, S3 backend needed for prod.
4. **API pose processing** — thread pool prevents event loop blocking but CPU saturation under high concurrency remains. Acceptable for MVP (<100 users).

---

## Error & Rescue Map

### Method-Level Error Paths

```
METHOD/CODEPATH               | WHAT CAN GO WRONG                | EXCEPTION CLASS
------------------------------|----------------------------------|---------------------------
API: POST /analyze            | Video too large (>100MB)         | FastAPI RequestValidationError
                              | Invalid MIME type                | ValueError (custom)
                              | Rate limit exceeded              | HTTPException(429)
                              | Video duration >30s              | ValueError (custom)
                              | Pose extraction fails (bad vid)  | PoseExtractionError
                              | Front-view video rejected        | PipelineError
                              | Scoring fails (angles OOB)       | ValueError
                              | Celery broker down (Redis)       | kombu.exceptions.OperationalError
------------------------------|----------------------------------|---------------------------
Worker: process_video         | LLM all providers fail           | coaching.AllProvidersFailedError
                              | LLM returns malformed JSON       | coaching.ResponseValidationError
                              | LLM returns empty response       | coaching.EmptyResponseError
                              | LLM hallucinates invalid angle   | coaching.HallucinationError
                              | LLM returns medical advice       | coaching.ContentGuardrailError
                              | Qdrant unreachable               | qdrant_client.QdrantException
                              | Qdrant returns empty results     | (not an error — empty list)
                              | Worker timeout (>30s)            | celery.SoftTimeLimitExceeded
                              | Worker crash (OOM on big video)  | celery.WorkerLostError
                              | blob/ upload fails               | IOError / botocore.ClientError
                              | DB write fails                   | sqlalchemy.exc.OperationalError
------------------------------|----------------------------------|---------------------------
Coaching: generate()          | litellm timeout per provider     | litellm.Timeout
                              | litellm rate limit               | litellm.RateLimitError
                              | litellm auth failure             | litellm.AuthenticationError
                              | Response not valid JSON          | json.JSONDecodeError
                              | Response missing required fields | pydantic.ValidationError
                              | Response contradicts biomech     | coaching.HallucinationError
------------------------------|----------------------------------|---------------------------
Scoring: score()              | BiomechanicalFeatures has NaN    | ValueError
                              | Unknown lift_type                | KeyError
------------------------------|----------------------------------|---------------------------
Overlay: generate_keyframes() | cv2 can't read video             | cv2.error
                              | No frames extracted              | ValueError
                              | PIL fails on image composition   | PIL.UnidentifiedImageError
```

### Rescue Actions

```
EXCEPTION CLASS                | RESCUED? | RESCUE ACTION                    | USER SEES
-------------------------------|----------|----------------------------------|------------------
PoseExtractionError            | Y        | Return 422 + message             | "Could not process video"
PipelineError                  | Y        | Return 422 + message             | "Re-film from the side"
kombu.OperationalError         | Y        | Return 503 + retry header        | "Service temporarily unavailable"
AllProvidersFailedError        | Y        | Fallback to rule-based coaching   | Rule-based tips only
ResponseValidationError        | Y        | Retry once, then rule-based      | Rule-based tips only
HallucinationError             | Y        | Strip hallucinated claims, retry | Coaching sans bad claims
ContentGuardrailError          | Y        | Filter keywords, regenerate      | Filtered coaching
QdrantException                | Y        | Skip RAG, coaching from biomech  | Coaching (no similar lifts)
SoftTimeLimitExceeded          | Y        | Mark analysis "failed"           | "Processing timed out"
WorkerLostError                | Y        | Periodic cleanup marks as failed | "Processing failed"
litellm.Timeout                | Y        | Next provider in chain           | Transparent
litellm.RateLimitError         | Y        | Next provider in chain           | Transparent
litellm.AuthenticationError    | Y        | Next provider + log ERROR        | Transparent (but alerted)
cv2.error                      | Y        | Skip overlay, return text only   | Coaching without keyframes
```

### Failure Modes Registry

```
CODEPATH           | FAILURE MODE           | RESCUED? | TEST? | USER SEES?        | LOGGED?
-------------------|------------------------|----------|-------|-------------------|--------
API /analyze       | Redis broker down      | Y        | PLAN  | 503 retry later   | Y
API /analyze       | Bad video file         | Y        | PLAN  | 422 + message     | Y
API /analyze       | Front-view rejected    | Y        | PLAN  | 422 + "re-film"   | Y
API /analyze       | Video >30s duration    | Y        | PLAN  | 422 + message     | Y
Worker             | All LLM providers fail | Y        | PLAN  | Rule-based tips   | Y
Worker             | LLM malformed JSON     | Y        | PLAN  | Retry/rule-based  | Y
Worker             | LLM hallucination      | Y        | PLAN  | Filtered coaching | Y
Worker             | Qdrant down            | Y        | PLAN  | Coaching (no RAG) | Y
Worker             | Worker timeout >30s    | Y        | PLAN  | "Timed out"       | Y
Worker             | Worker crash           | Y        | PLAN  | "Failed" (cleanup)| Y
Coaching           | Prompt injection (RAG) | Y        | PLAN  | Sanitized output  | Y
```

No CRITICAL GAPS. Two gaps identified during review (Redis broker, RAG injection) and resolved.

---

## Security & Threat Model

| Threat | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Video upload: oversized file | High | Med (OOM/disk) | 100MB limit enforced in FastAPI middleware |
| Video upload: malicious file (not video) | Med | High | MIME type check + cv2 safely fails on non-video |
| LLM prompt injection via video metadata | Low | Med | Video metadata doesn't enter prompt — biomechanical features are numeric |
| Direct object reference (UUID guessing) | Med | Low | UUIDs are 128-bit random, infeasible to guess. Rate limit /results/ |
| **LLM prompt injection via RAG comments** | **Med** | **High** | **Sanitize RAG comments before LLM prompt — strip instruction-like patterns** |
| Denial of service: large/long video | Med | Med | 100MB + 30s duration limit + worker timeout (30s soft limit) |
| Secrets in env | — | — | All via env vars, not hardcoded |
| No auth for MVP | — | Low | UUID-based anonymous access acceptable for v1 |

### RAG Comment Sanitization (accepted mitigation)

Reddit comments from scraped training data enter the LLM prompt as "similar lift
feedback." A crafted comment could manipulate LLM output. Mitigation: strip
instruction-like patterns from comments before including in prompt. Simple regex +
length limit. Implemented in `coaching/sanitizer.py`.

---

## Data Flow

### Primary Flow: Video Upload → Coaching

```
INPUT (video)──▶ VALIDATE ──▶ BLOB STORE ──▶ POSE PIPELINE ──▶ SCORING ──▶ INSTANT TIPS
    │               │              │               │               │            │
    ▼               ▼              ▼               ▼               ▼            ▼
 [>100MB?]     [not video?]  [disk full?]    [no landmarks?]  [NaN angles?] [returned]
 [0 bytes?]    [bad MIME?]   [write fail?]   [front view?]    [unknown lift?]
 [>30s?]                                     [too short?]

                                    ──── Celery task (async) ────
                                    │
FEATURES ──▶ RAG SEARCH ──▶ COACHING (LLM) ──▶ OVERLAY ──▶ PERSIST ──▶ POLL → RESULTS
    │             │               │                │           │            │
    ▼             ▼               ▼                ▼           ▼            ▼
 [passed       [Qdrant down?] [all providers   [cv2 fails?] [DB down?]  [task not
  via Celery]  [0 results?]    fail?]          [0 frames?]  [blob fail?] found?]
                               [malformed JSON?]                         [still pending?]
                               [hallucination?]
                               [medical advice?]
```

### Interaction Edge Cases

```
INTERACTION              | EDGE CASE                | HANDLED? | HOW?
-------------------------|--------------------------|----------|----------------------------------
Video upload             | Double-click submit      | PLAN     | Disable button after click (FE)
                         | Upload during deploy     | PLAN     | Graceful 503 with retry header
                         | 0-byte file              | PLAN     | Validate Content-Length > 0
                         | Video with no frames     | YES      | PoseExtractionError → 422
                         | Very long video (>30s)   | PLAN     | Enforce max duration
Status polling           | Task not found           | PLAN     | 404 with message
                         | Task stuck (worker died) | PLAN     | Cleanup job marks failed after 5m
                         | Poll after result ready  | PLAN     | Return "complete" + result URL
Results page             | Results not yet ready    | PLAN     | 404 or "still processing"
                         | Results expired/deleted  | PLAN     | 404 with "analysis not found"
History page             | Zero analyses            | PLAN     | Empty state with CTA
                         | UUID cookie cleared      | PLAN     | New UUID, empty history (v1 OK)
```

---

## Test Strategy

### Coverage Plan

| Module | Unit Tests | Integration Tests | What to test |
|---|---|---|---|
| `blob/local.py` | upload/download round-trip, get_url, missing file, path traversal | — | 5-6 tests |
| `scoring/scorer.py` | Known angles → grades, boundary values, NaN, unknown lift | — | 8-10 tests |
| `coaching/generator.py` | Mock litellm → valid response, fallback chain, all-fail → rules | Auto-invalidating cassettes | 8-10 unit + 3-4 cassette |
| `coaching/validation.py` | Valid JSON, missing fields, hallucinated angles, medical keywords | — | 6-8 tests |
| `coaching/sanitizer.py` | Clean passthrough, injection stripped, length limit | — | 4-5 tests |
| `overlay/keyframes.py` | Frame extraction, skeleton drawing, color coding | — | 5-6 tests |
| `api/routes.py` | Upload happy path, oversized, bad MIME, rate limit, 422 | Full stack test client | 8-10 tests |
| `worker/tasks.py` | Mock all deps, timeout, failure marking | Full pipeline (devcontainer) | 5-6 unit + 2-3 integration |
| `pose/lift_classifier.py` | Squat features → "squat", deadlift → "deadlift", ambiguous → None | — | 5-6 tests |

### LLM Testing: Auto-Invalidating Cassettes

Store the **prompt template** (system prompt + structure, not the rendered prompt with
specific angles) alongside the LLM response in a cassette file. On each test run:

1. Render the current prompt template
2. Compare to the stored template in the cassette
3. If **match**: replay the stored response (fast, free, deterministic)
4. If **mismatch**: call the real LLM, record the new response, update the cassette

Key: compare **templates**, not rendered prompts. The rendered prompt includes dynamic
data (specific angles, RAG results) that changes every invocation. The template is what
we want to track for invalidation.

### Confidence Tests

- **2am Friday test:** Upload a real video via test client, assert response contains form grade, coaching text, and at least one keyframe URL
- **Hostile QA test:** Upload 0-byte file, PNG renamed to .mp4, 10-minute video, front-facing video — all return meaningful errors, not 500s

---

## Observability Plan

### Structured Logging (accepted expansion)

All new modules instrumented with `structlog`, JSON output, `video_id` as trace key.

| Module | Log Events | Key Fields |
|---|---|---|
| `api/` | request_received, upload_validated, pose_complete, task_queued, result_served | video_id, user_uuid, lift_type, duration_ms |
| `scoring/` | score_computed | video_id, overall_grade, per_criterion |
| `coaching/` | provider_attempted, provider_failed, provider_succeeded, response_validated, hallucination_detected, fallback_to_rules | video_id, provider, tokens, latency_ms, retry_count |
| `worker/` | task_started, task_stage_complete, task_succeeded, task_failed | video_id, task_id, stage, duration_ms, error |
| `blob/` | upload_complete, download_complete | video_id, key, size_bytes |
| `overlay/` | keyframes_generated | video_id, frame_count |

### Day-1 Metrics

- Analyses per hour
- p50/p95 total processing time
- LLM provider success/failure rates
- Form grade distribution

### Alerts

- Processing time p95 > 15s
- LLM all-providers-failed rate > 5%
- Worker queue depth > 20

---

## Performance Notes

| Concern | Assessment | Action |
|---|---|---|
| MediaPipe model loading | ~200ms per `PosePipeline()` instantiation | Make singleton via FastAPI `Depends()` |
| Video in memory | 100MB max read into memory | Use `SpooledTemporaryFile` with threshold |
| API blocking | Pose pipeline blocks 2-3s per request | `run_in_executor()` thread pool |
| DB indexes | `analyses` table queried by user_uuid and video_id | Index both columns |
| Worker total time | ~6-7s (pose 3s + LLM 2-3s + overlay 1s) | Within 30s soft limit |
| Connection pools | DB default 5 connections, Qdrant single per worker | Fine for MVP |

---

## Implementation Order

1. Add Redis to devcontainer (P0 blocker)
2. `blob/` — storage protocol + local backend
3. `scoring/` — FormScorer + thresholds
4. `pose/lift_classifier.py` — auto-detection heuristic
5. `coaching/` — LLM generator + validation + sanitizer + cassette utility
6. `overlay/` — keyframe extraction + annotation
7. `worker/` — Celery task definitions
8. `api/` — FastAPI endpoints + UUID system
9. Structured logging — instrument all modules

Bottom-up: each module is testable in isolation before integration.

---

## What Already Exists (reuse map)

| Sub-problem | Existing code | Reuse |
|---|---|---|
| Video → biomechanical features | `pose/pipeline.py` (complete, 7 test files) | Full — API + worker |
| Similar lift retrieval | `rag/store.py` (complete, 13 tests) | Full — worker |
| Metadata persistence | `db/` (models + repository, 2 test files) | Extend with analyses table |
| CLI orchestration | `cli.py` (scrape + pose-process) | Extend with new commands |
| App config | `config.py` (AppConfig) | Extend with redis_url, blob config, LLM keys |

---

## Dream State Delta

This plan gets us from "data pipeline" to "working coaching app" — approximately 60%
of the way to the 12-month ideal. What remains: mobile app, real-time feedback, social
features, coach marketplace. The modular architecture supports all of these as
extensions rather than rewrites.

```
CURRENT STATE                    THIS PLAN                       12-MONTH IDEAL
─────────────────────────────    ───────────────────────────     ──────────────────────────
Data pipeline only               End-to-end coaching app          Platform
• Scrape Reddit posts            • Upload video → get coached     • Real-time mobile feedback
• Extract pose landmarks         • Form grade A-F                 • Multi-rep tracking
• Store vectors in Qdrant        • Annotated keyframes            • Social sharing/leaderboard
• No user-facing output          • LLM coaching text              • Custom training plans
                                 • Instant rule-based tips        • Coach marketplace
                                 • Auto-detected lift type        • Integration w/ training apps
                                 • Progress tracking (UUID)
                                 • Structured logging
```
