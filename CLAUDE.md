# CLAUDE.md — Groundwork

Engineering reference for the Groundwork codebase. Read this before making changes.

---

## What This Is

Groundwork is a camera-to-estimate tool for residential contractors. A contractor takes a photo of a room, records a voice note describing the scope, and receives a line-item cost estimate and a PDF proposal.

**Deployed:**
- Backend API: Railway (`groundworks-api` service)
- Celery worker: Railway (`clery-worker` service)
- Redis: Railway managed Redis
- Mobile: Expo app (physical device via Expo Go or EAS build)

---

## Repository Layout

```
groundwork/
├── api/                   # Flask backend — deploy root for Railway
│   ├── app.py             # Flask app factory, limiter, blueprints, request logging
│   ├── celery_worker.py   # Celery app factory
│   ├── config.py          # All config from env vars; RATELIMIT_ENABLED=False in testing
│   ├── logging_config.py  # Structured logging setup
│   ├── middleware/
│   │   └── auth.py        # require_auth / optional_auth JWT decorators (ES256, Supabase)
│   ├── routes/
│   │   ├── estimate.py    # POST /estimate, GET /estimate/status/:id, GET /estimates/recent
│   │   ├── proposal.py    # POST /proposal
│   │   ├── rooms.py       # POST /rooms, GET /projects, GET /projects/:id
│   │   └── upload.py      # POST /upload/presign
│   ├── tasks/
│   │   ├── vision_pipeline.py  # Main Celery task (5-step AI pipeline)
│   │   └── proposal_task.py    # PDF generation Celery task
│   ├── services/
│   │   ├── claude_vision.py        # classify_room(), generate_work_items(), extract_voice_scope()
│   │   ├── yolo_detect.py          # Local YOLOv8s — detect_objects_multi()
│   │   ├── depth_estimator.py      # Depth Anything V2 Small — compute_measurements()
│   │   ├── whisper_transcribe.py   # faster-whisper local STT
│   │   ├── quantity_estimator.py   # estimate_quantities()
│   │   ├── pricing_engine.py       # calculate_estimate(), calculate_all_tiers()
│   │   ├── serpapi_prices.py       # fetch_hd_price(), fetch_hd_prices() — Redis-cached
│   │   ├── s3_storage.py           # upload, download, presigned URLs, preprocessing keys
│   │   ├── pdf_generator.py        # build_proposal_pdf() — ReportLab
│   │   ├── image_preprocessor.py   # preprocess() — HEIC->JPEG via pillow-heif, resize, EXIF strip
│   │   └── video_processor.py      # frame extraction from video
│   ├── models/
│   │   └── supabase_models.py      # All Supabase CRUD: room_scans, estimates, proposals, projects
│   ├── tests/
│   │   ├── conftest.py             # Session-scoped Flask app, RATELIMIT_ENABLED=False, env stubs
│   │   ├── unit/                   # test_s3_storage, test_pricing_engine, test_serpapi_prices,
│   │   │                           # test_claude_vision, test_pdf_generator, test_auth
│   │   └── integration/            # test_estimate_routes, test_proposal_routes,
│   │                               # test_rooms_routes, test_upload_routes
│   ├── Dockerfile                  # python:3.12-slim; pre-downloads Whisper/YOLO/Depth weights
│   ├── docker-compose.yml          # Local dev: api + worker + redis
│   ├── requirements.txt
│   ├── requirements-test.txt       # pytest + pytest-mock
│   └── pytest.ini
│
└── groundwork-app/        # Expo React Native app
    └── src/
        ├── app/           # expo-router screens (file = route)
        │   ├── _layout.tsx
        │   ├── index.tsx       # Home screen
        │   ├── camera.tsx      # Camera capture + multi-photo
        │   ├── capture.tsx     # Photo review before submit
        │   ├── scanning.tsx    # Animated polling screen
        │   ├── result.tsx      # Detection result + project picker
        │   ├── estimate.tsx    # Estimate breakdown (Economy/Standard/Premium tabs)
        │   └── proposal.tsx    # PDF proposal preview + download
        └── services/
            ├── api.ts          # groundworkApi client — all typed API calls
            ├── upload.ts       # S3 presigned upload flow
            └── estimateStore.ts # In-memory session state (estimate result + project client)
```

---

## Vision Pipeline (`tasks/vision_pipeline.py`)

The main Celery task runs these steps in sequence. Each step is wrapped in `_step()` / `_done()` for timing logs.

| Step | Function | Notes |
|------|----------|-------|
| Preprocess | `_download_and_preprocess()` | Downloads S3 keys, converts HEIC->JPEG via pillow-heif, resizes to <=2048px, uploads preprocessed back to S3 |
| Audio | `whisper_transcribe.transcribe()` | Runs if `s3_audio_key` provided; downloads audio from S3 then transcribes locally |
| 1 | `claude_vision.classify_room()` | Returns `{room_type, confidence, condition, detected_features}` |
| 1.5 | `claude_vision.generate_work_items()` | 2nd Claude call — synthesises visual features + voice transcript into definitive work items list |
| 2 | `yolo_detect.detect_objects_multi()` | Local YOLOv8s; results used as depth scale anchors |
| 3 | `depth_estimator.compute_measurements()` | Depth Anything V2 Small; produces `floor_area_sqft`, `room_width_ft`, `room_depth_ft` |
| 4 | `quantity_estimator.estimate_quantities()` | Merges AR data -> depth measurements -> pixel heuristics (priority order) |
| 5 | `pricing_engine.calculate_all_tiers()` | Fetches live HD prices once (SerpApi, Redis-cached 6hr), calculates eco/standard/premium in one pass |
| Save | `supabase_models.*` | Saves room_scan, estimate, and estimate_line_items to Supabase |

Room-type validation filter runs after Step 1.5 — removes items not valid for the detected room type to prevent hallucinated cross-room items.

Fallback: if S3 preprocess fails (e.g. unsupported image format), the pipeline continues with voice-only scope and hardcoded fallback detected items.

---

## Key Constraints and Decisions

**`_parse_json()` in `claude_vision.py` only accepts dicts.** Arrays trigger `_JsonParseError` and cause a retry. This guard runs in all three parse paths (direct, markdown fence, `{...}` search).

**`calculate_all_tiers()` returns `{'eco', 'standard', 'premium'}` keys** — not `'economy'`. The pipeline maps `eco` -> `economy` in the response JSON for the client.

**`calculate_estimate()` does not add `confidence` or `tier` keys** — those come from the vision pipeline layer that calls it.

**Rate limiting is disabled in tests.** `config.py` sets `RATELIMIT_ENABLED = FLASK_ENV != 'testing'`. The `conftest.py` sets `FLASK_ENV=testing` before any imports.

**Upload route patches must target `routes.upload.*`** for module-level imports (`generate_presigned_put`, `create_room_scan`). Lazy imports inside the function body (`get_room_scan`, `update_room_scan`) patch at `models.supabase_models.*`.

**Supabase client is lazy** — `get_db()` only connects on first DB call. Tests mock `supabase.create_client` at session scope.

**`pillow-heif` is registered at import time** in `image_preprocessor.py` via `pillow_heif.register_heif_opener()`. This lets `Image.open()` handle iPhone `.heic` files transparently.

**Railway deployment:**
- Port binding: Dockerfile `CMD` uses `${PORT:-5001}` — Railway injects `$PORT`, falls back to 5001 for local Docker
- `REDIS_URL` must be a Railway reference variable `${{Redis.REDIS_URL}}` — not the Docker Compose `redis://redis:6379/0`
- API service: no start command override (uses Dockerfile CMD)
- Worker service: start command `celery -A celery_worker worker --loglevel=info --concurrency=2`

---

## Running Tests

```bash
cd api
python3 -m pytest tests/ -q
# 245 passed
```

Dependencies needed in addition to `requirements.txt`:
```bash
pip install pytest pytest-mock
```

---

## Environment Variables

See `api/.env.example` for the full list. Required at runtime:

- `ANTHROPIC_API_KEY` — Claude Vision
- `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` + `SUPABASE_JWT_SECRET`
- `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `S3_BUCKET` + `S3_REGION`
- `REDIS_URL`

Optional (graceful fallback if missing):
- `OPENAI_API_KEY` — GPT-4o fallback for Claude failures only
- `SERPAPI_KEY` — live HD prices; falls back to hardcoded RSMeans tables

---

## Database Schema

Six tables. All IDs are UUIDs. Created via Supabase SQL Editor (no ORM migrations).

```
projects          — top-level project per job site
room_scans        — one per camera capture session
estimates         — one per room_scan; stores full pipeline output as raw_response JSONB
estimate_line_items — one row per line item in the estimate
proposals         — PDF proposal records
project_rooms     — join table: project <-> room_scan + estimate, with total_estimate cache
```

`project_rooms` has a `UNIQUE (project_id, room_scan_id)` constraint — adding the same scan twice is a no-op.

---

## Mobile App

**Navigation:** expo-router file-based. Flow: `index -> camera -> capture -> scanning (polls) -> result -> estimate -> proposal`

**State between screens:** `estimateStore.ts` holds the completed estimate result and selected project client in module-level variables (resets on app restart). Not persisted.

**API base URL:** `EXPO_PUBLIC_API_URL` in `groundwork-app/.env`. For local dev, use your machine's LAN IP (not `localhost`) so the physical device can reach the Flask server.

**Multi-photo flow:** First upload creates a `room_scan_id`. Subsequent uploads pass `room_scan_id` back to append image URLs to the same scan.

**Proposal PDF:** Generated server-side by ReportLab, uploaded to S3, returned as a presigned URL. The mobile app opens it in the system browser.

**Project client in PDF:** Set via `setProjectClient()` in `result.tsx` after the user links an estimate to a project. `proposal.tsx` reads it via `getProjectClient()` and merges it into the proposal form.
