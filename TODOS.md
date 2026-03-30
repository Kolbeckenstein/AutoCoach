# TODOS

## Pose Pipeline

### Extend PhaseDetector for multi-rep sets

**What:** Extend `PhaseDetector` to detect multiple reps in a single video (currently detects one descent/bottom/ascent cycle).

**Why:** Most form check videos contain 3-5 reps. Per-rep analysis enables "best rep / worst rep" comparisons and detecting form degradation across a set — genuinely useful coaching that text alone can't provide.

**Context:** Current `PhaseDetector.detect()` finds a single argmax of the depth ratio series. Multi-rep detection requires finding multiple peaks (scipy.signal.find_peaks or a rolling-window approach on the smoothed depth ratio). Return `list[list[PhaseSegment]]` — one [descent, bottom, ascent] triplet per rep. Downstream consumers (normalizer, biomechanics, scoring) would process each rep independently.

**Effort:** M
**Priority:** P2
**Depends on:** Pose pipeline tests (P0 TODO above)

---

## New Modules

### ~~Build blob/ storage abstraction~~

Completed 2026-03-19. `BlobStorage` Protocol with `LocalBlobStorage` filesystem backend. 16 tests, 100% coverage. Includes path traversal and absolute path security validation.

---

### Build scoring/ module (Form Score A-F)

**What:** A `FormScorer` that takes `BiomechanicalFeatures` and returns an A-F grade with per-criterion breakdown (depth, knee tracking, back angle, tempo).

**Why:** The form score is the most shareable, gamifiable output. It makes AutoCoach sticky — users come back to improve their grade. It's also cheap (no LLM needed, pure rules) and instant (<10ms).

**Context:** Scoring criteria by lift type: Squat — depth (hip crease vs knee, available as `min_hip_angle`), knee tracking (knee valgus, detectable from left/right knee x-spread if both sides visible), back angle (`max_back_angle`). Thresholds will need tuning with real data. Output model: `FormScore(overall_grade: str, criteria: list[CriterionScore], confidence: float)`. Consider making thresholds configurable per lift type via a YAML/JSON config so domain experts can tune without code changes.

**Effort:** M
**Priority:** P1
**Depends on:** Pose pipeline tests (P0 TODO)

---

### Build overlay/ module (Annotated Keyframes)

**What:** Extract 3-5 key frames from a video, draw color-coded skeleton overlays using OpenCV, return as annotated PNG images.

**Why:** Visual feedback is the core differentiator. A picture of your skeleton with the knee highlighted in red is worth 1000 words of LLM coaching text. This is the "show, don't tell" feature.

**Context:** Key frames to extract: worst moment (lowest per-frame score), best moment (highest per-frame score), deepest point (min hip angle frame), lockout (last frame of ascent). Draw MediaPipe 33-point skeleton connections using OpenCV `cv2.line()` + `cv2.circle()`. Color code: green=good (angle within A-B range), yellow=warning (C range), red=danger (D-F range). Add text annotations with angle values. Handle different video resolutions by scaling skeleton line thickness proportionally. Output: list of PNG byte buffers + captions.

**Effort:** M
**Priority:** P1
**Depends on:** Pose pipeline tests (P0 TODO), scoring module

---

### Build coaching/ module (LLM integration with structured output)

**What:** LLM coaching generator using litellm with structured JSON output, response validation, and content guardrails.

**Why:** LLM-generated coaching is the premium feature that synthesizes biomechanical data with community knowledge from RAG results into personalized, actionable feedback.

**Context:** Key design decisions from CEO plan review (2026-03-17): (1) Force structured JSON output with schema: `{cues: [{text: str, severity: "safety"|"form"|"optimization", related_angle: str, frame_idx: int}], summary: str, safety_warnings: list[str]}`. (2) Validate LLM output against biomechanical data — if LLM claims "knee angle is 45°" but actual is 90°, reject and retry. (3) Filter for medical advice keywords. (4) Per-provider timeout of 5-10s (not 30s default) to avoid 60s+ waits on cascade failure. (5) Fallback to rule-based coaching (from scoring module cues) when all providers fail. (6) Provider chain: Claude Haiku → GPT-4o-mini → Gemini Flash. (7) Use sync `litellm.completion()` in worker. (8) **Sanitize RAG comments** before including in prompt — strip instruction-like patterns to mitigate prompt injection. (9) **Auto-invalidating LLM test cassettes** — store prompt template alongside response, auto-re-record when template changes. Compare templates (not rendered prompts with dynamic angles) for invalidation.

**Effort:** L
**Priority:** P1
**Depends on:** Scoring module, blob/ storage

---

### Build API layer (FastAPI endpoints)

**What:** FastAPI backend with video upload, processing status polling, results retrieval, and history endpoints.

**Why:** This is the user-facing interface that connects the processing pipeline to the frontend.

**Context:** Endpoints: `POST /api/v1/analyze` (video upload + queue processing), `GET /api/v1/status/{task_id}` (poll Celery task status), `GET /api/v1/results/{video_id}` (full CoachingReport), `GET /api/v1/history` (user's past analyses by UUID). Key implementation notes: (1) Add `user_uuid` from HTTP-only cookie or generate on first request. (2) Validate upload: max 100MB, MIME type check, rate limit, max 30s video duration. (3) `lift_type` parameter optional — auto-detected if omitted (CEO review expansion #2), validated against enum if provided. (4) Add `analyses` table: `user_uuid, video_id, lift_type, form_score, created_at`. (5) Return `CoachingReport` as the unified output contract. (6) **API does pose+scoring synchronously** (via `run_in_executor()` thread pool), returns instant rule-based tips immediately (CEO review expansion #1), then queues Celery task with serialized `BiomechanicalFeatures` for RAG+LLM+overlay. (7) **PosePipeline as singleton** — use FastAPI `Depends()` to avoid re-loading MediaPipe model per request. (8) Results stored in PostgreSQL (metadata + text) + blob/ (keyframe images).

**Effort:** L
**Priority:** P1
**Depends on:** blob/ storage, coaching module, scoring module

---

### Build worker/ module (Celery task orchestration)

**What:** Celery task definitions for video processing pipeline with timeout handling and dead letter recovery.

**Why:** Video processing takes 3-6 seconds — too long for a synchronous API request. Background workers enable async processing with status polling.

**Context:** Primary task: `process_video(features_json, video_key, user_uuid)` — receives pre-computed `BiomechanicalFeatures` (serialised JSON from the API), runs RAG + LLM coaching + overlay + persist. API already did pose+scoring. Must handle: (1) `SoftTimeLimitExceeded` — mark analysis as "failed" with user-visible message. (2) Worker crash — periodic cleanup job marks tasks stuck in "processing" for >5 minutes as "failed". (3) Use sync `litellm.completion()`. (4) Qdrant down — graceful degradation (skip RAG, generate coaching from biomechanics + scoring only). (5) Progress updates via Celery task state. (6) Redis broker unavailable — API catches `OperationalError`, returns 503.

**Effort:** M
**Priority:** P1
**Depends on:** All processing modules

---

## Infrastructure

### Add anonymous user UUID system

**What:** Assign a UUID on first API request, store in HTTP-only cookie, create `analyses` table linking user_uuid → video_id → results.

**Why:** Enables progress tracking ("your depth improved 12° since last month") without the complexity of user authentication. The expanded vision's progress tracking and history features depend on this.

**Context:** No signup, no password, no email. UUID generated server-side on first request if no cookie present. Alembic migration adds `analyses` table with columns: `id (UUID PK), user_uuid (UUID, indexed), video_id (str), lift_type (str), form_score (str), created_at (timestamp)`. Frontend stores UUID in localStorage as backup (in case cookies are cleared). Consider: users who clear cookies lose their history — acceptable for v1, add optional email recovery in v2.

**Effort:** S
**Priority:** P1
**Depends on:** API layer

---

### DRY up landmark index constants

**What:** Extract MediaPipe landmark indices (`LEFT_HIP = 23`, etc.) from `phases.py`, `filters.py`, and `biomechanics.py` into a shared `pose/landmarks.py` constants module.

**Why:** Same constants defined independently in 3 files. If MediaPipe changes landmark numbering (unlikely but possible), all three files need updating. Violates DRY.

**Context:** Create `pose/landmarks.py` with all 33 MediaPipe landmark indices as module-level constants. Import from the shared module in `phases.py`, `filters.py`, and `biomechanics.py`. Also move the axis index constants (`_X = 0`, `_Y = 1`, `_VIS = 3`) to the shared module.

**Effort:** S
**Priority:** P2
**Depends on:** Pose pipeline tests (to verify refactor doesn't break anything)

---

## Documentation

### Update stale documentation

**What:** Update ARCHITECTURE.md, README.md, and IMPLEMENTATION_PLAN.md to reflect current codebase and expanded vision.

**Why:** Docs reference `transformer/` (renamed to `pose/`), show SQLite code (actual uses SQLAlchemy + PostgreSQL), and don't reflect the expanded vision (scoring, overlay, progress tracking). Stale docs are worse than no docs.

**Context:** Specific fixes needed: (1) ARCHITECTURE.md — update system diagram with scoring/, overlay/, blob/ modules; update schema to match SQLAlchemy models; replace transformer references with pose/. (2) README.md — update project structure to match actual code; update phase status. (3) IMPLEMENTATION_PLAN.md — update Phase 1 code to match actual implementation (SQLAlchemy not SQLite); add expanded vision features (scoring, overlay, progress tracking) to Phases 4-5; fix the `await` in Celery task. (4) Add expanded system architecture diagram from this review.

**Effort:** S
**Priority:** P2
**Depends on:** Decisions from CEO plan review (this document)

---

### Add structured logging + trace IDs

**What:** Add `structlog` or Python `logging` with JSON output to every pipeline stage, using `video_id` as trace ID.

**Why:** Currently zero way to debug "why did video X get a bad score." Need to see which phases were detected, what angles were computed, what RAG returned, what the LLM was asked and responded. Promoted from P2 to P1 in CEO plan review (2026-03-17) — cheaper to build in as modules are created than to retrofit.

**Context:** Log at each pipeline stage: (1) PoseExtractor — frame count, fps, duration. (2) ViewClassifier — lateral spread, view class, dominant side. (3) PhaseDetector — phase boundaries (start_idx, end_idx per phase). (4) BiomechanicsExtractor — min/max angles. (5) FormScorer — per-criterion scores, overall grade. (6) QdrantStore — query vector summary, result count, top scores. (7) CoachingGenerator — provider attempted, tokens used, response validated. All logs keyed by `video_id` for correlation.

**Effort:** S
**Priority:** P1
**Depends on:** None

---

## Vision / Delight

### Lift type auto-detection

**What:** Detect squat/bench/deadlift automatically from pose sequence instead of requiring user selection.

**Why:** Small touch, big "oh nice" moment. Removes a decision point from the upload flow. Promoted from P3 to P1 in CEO plan review (2026-03-17).

**Context:** Heuristics using data already in BiomechanicalFeatures: Squat — symmetric hip/knee descent pattern, standing start position. Deadlift — hip-y near ankle-y in early frames (bar starts on floor), hip hinge dominant. Bench press — horizontal torso angle throughout. Could also use the body orientation (standing vs lying down) from the first frame. ~30 min to implement as a classifier on top of existing features. Fallback to user selection if confidence < threshold. API accepts optional `lift_type` param — if omitted, auto-detects.

**Effort:** S
**Priority:** P1
**Depends on:** Pose pipeline (exists)

---

### Best rep / worst rep selector (multi-rep analysis)

**What:** For multi-rep sets, identify the cleanest and worst reps and highlight the difference.

**Why:** Users don't realize their form degrades over a set. "Rep 1 was A-, Rep 4 was C+ — your knees started caving" is genuinely useful coaching.

**Context:** Depends on multi-rep PhaseDetector extension (P2 TODO). Once multiple reps are segmented, run FormScorer on each independently. Present: best rep keyframe, worst rep keyframe, delta in scores and specific angles that changed.

**Effort:** M
**Priority:** P3
**Depends on:** Multi-rep PhaseDetector, scoring module

---

### Quick tips without LLM (coaching cue database)

**What:** Curated database of coaching cues mapped to specific form issues, served instantly without LLM.

**Why:** <100ms response for common issues vs 1-3s for LLM. The instant tips feel magical. LLM provides deeper analysis on top.

**Context:** Source the cue database FROM the scraped Reddit data: filter comments with score ≥ 10, use LLM in a one-time batch job to extract structured cues: `{issue: "knee_cave", cue: "spread the floor", lift_type: "squat", source_comment_id: "abc123"}`. Additional sources: r/fitness wiki, r/weightroom wiki, Stronger By Science articles (publicly accessible). Store as a JSON/YAML config file that maps (lift_type, issue) → list of coaching cues with attribution.

**Effort:** M
**Priority:** P3
**Depends on:** Scoring module (to detect issues), scraped data (to mine cues)

---

### Shareable form card image

**What:** Generate a single summary image: form grade, key metrics, annotated skeleton, coaching cues — designed for social sharing.

**Why:** Marketing that builds itself. Every shared form card shows AutoCoach to the user's gym community.

**Context:** PIL/Pillow template with fixed layout: large letter grade top-left, metrics panel, skeleton keyframe, cue text. Sized for Instagram stories (1080×1920) and standard sharing (1200×630). Add subtle AutoCoach branding. ~1-2 hours to build once overlay and scoring modules exist.

**Effort:** S
**Priority:** P3
**Depends on:** Overlay module, scoring module

---

### Progress sparkline on history page

**What:** Tiny inline chart next to each lift type showing form score trend over time.

**Why:** Makes the history page feel alive. Users instantly see if they're trending up or down.

**Context:** Frontend-only feature. Use a lightweight charting library (e.g., sparkline component in React). Data comes from the history API endpoint (list of analyses with form_score and created_at). Example: "Squat: C → C+ → B- → B ▲".

**Effort:** S
**Priority:** P3
**Depends on:** History API endpoint, anonymous UUID system

---

## New from CEO Review (2026-03-17)

### ~~Add Redis to devcontainer~~

Completed 2026-03-19. Redis `7-alpine` already in docker-compose. Added `redis_url` property to `AppConfig`.

---

### Add coaching tone selector

**What:** Users choose a coaching personality: Encouraging, Technical, or Drill Sergeant.

**Why:** Fun differentiator, makes the product feel personal. Deferred from CEO review — not essential for v1.

**Context:** Three system prompt variants + a `tone` parameter on the API. Zero architectural change, purely prompt engineering.

**Effort:** S
**Priority:** P3
**Depends on:** coaching/ module

---

## New from Eng Review (2026-03-26)

### Extend PhaseDetector for non-squat lifts before v0.5

**What:** Either extend `PhaseDetector` to handle deadlift/bench phase detection, or gate non-squat lifts with a clear warning ("Squat scoring is validated; deadlift/bench scoring is experimental") in v0.5's lift type selector.

**Why:** `PhaseDetector.detect()` uses `argmax(hip_y - knee_y)` — this is squat-specific. For deadlift (starts bent, ends extended), the argmax fires at the wrong phase boundary. For bench press (horizontal body), `hip_y - knee_y` is undefined. v0.5 adds a lift type selector that accepts all three lifts, but the pipeline will silently produce garbage for non-squat lifts. Flagged by outside voice during eng review.

**Context:** Two approaches: (a) Quick fix — gate non-squat lifts with a warning banner and reduced confidence score. (b) Full fix — implement lift-specific phase detection heuristics (deadlift: track hip extension from low to high; bench: track elbow angle from flexed to extended). Option (a) is 15 minutes CC time; option (b) is ~1 hour CC time. Recommend (a) for v0.5, (b) for v1.

**Effort:** S (gate) / M (full fix)
**Priority:** P1
**Depends on:** v0.5 scoring module scope

---

## New from CEO Review (2026-03-23)

### Populate Qdrant with scraped Reddit data

**What:** Run existing scraper + embedding pipeline to populate Qdrant with Reddit coaching comments before v1b launch.

**Why:** v1b's RAG-powered LLM coaching depends on having a populated vector store. Without it, LLM coaching falls back to biomechanics-only prompts — functional but less rich. The scraper and embedding pipeline already exist; this is an operational task, not a code task.

**Context:** Existing `rag/store.py` and `rag/embeddings.py` modules (13 tests) handle Qdrant operations. The scraper exists from earlier work. Steps: (1) Run scraper against target subreddits (r/formcheck, r/weightroom, r/fitness). (2) Filter for comments with score ≥ 5. (3) Run embedding pipeline to vectorize and store in Qdrant. (4) Verify retrieval works with sample queries. If corpus is empty at v1b launch, LLM coaching still works (graceful degradation) — but quality is significantly better with RAG context.

**Effort:** S
**Priority:** P1
**Depends on:** v1a infrastructure (Qdrant running in docker-compose)

---

### Mount blob/ root as FastAPI StaticFiles

**What:** Configure FastAPI to serve the blob storage root directory as static files so keyframe image URLs are HTTP-accessible in HTML pages.

**Why:** `LocalBlobStorage.get_url()` returns absolute filesystem paths (e.g., `/app/data/keyframes/abc/frame_042.png`). These work for the pose pipeline (which takes `Path`), but v1b's overlay module generates keyframe PNGs that need to be served as `<img src="...">` in HTML. Without a StaticFiles mount, the browser can't access them.

**Context:** FastAPI's `StaticFiles` middleware can mount a directory at a URL prefix (e.g., `app.mount("/static/blob", StaticFiles(directory=blob_root))`). The API then constructs image URLs as `/static/blob/keyframes/{video_id}/frame_042.png`. This couples the API to `LocalBlobStorage`'s path format — acceptable for local dev. When S3 backend is added, keyframe URLs would be presigned S3 URLs instead, and the StaticFiles mount becomes unnecessary.

**Effort:** S
**Priority:** P1
**Depends on:** v1a API layer, overlay module (v1b)

---

### Extend BiomechanicalFeatures for bench press

**What:** Investigate and potentially extend `BiomechanicalFeatures` with bench-press-specific angles (elbow angle, bar path deviation) that aren't well-captured by the current squat-centric feature set.

**Why:** Current `BiomechanicalFeatures` measures hip angle, knee angle, and back angle — all designed for standing movements. For bench press (horizontal body), hip angle is meaningless and back angle captures arch rather than form quality. Scoring bench press with these features is possible but limited, which is why v0.5 shows an "experimental" caveat. Extending the feature set would unlock meaningful bench coaching.

**Context:** Potential new features: (1) Elbow angle at bottom position (measures touch point and range of motion). (2) Bar path deviation from vertical (measures efficiency). (3) Shoulder angle (measures flare). These require changes to `BiomechanicsExtractor` and downstream consumers (scoring, coaching prompts). May also need `ViewClassifier` adjustments for the supine body position. Research needed on whether MediaPipe landmark detection is reliable for a person lying on a bench.

**Effort:** M
**Priority:** P2
**Depends on:** v0.5 scoring module (to understand current scoring limitations in practice)

---

## Completed

### Unit tests for pose processing pipeline ~~(0% coverage)~~

Completed 2026-03-17. 183 tests passing across all pose/ and rag/ modules. Coverage includes: extractor, filters, phases, normalizer, biomechanics, pipeline, models, rag/embeddings, rag/store.
