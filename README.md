# Groundwork — Camera-to-Estimate™

A contractor walks into a room, takes a photo, speaks the scope, and receives a line-item cost estimate with a proposal ready to send. Under 5 minutes. No typing.

---

## The Problem

~800,000 licensed residential general contractors in the U.S. produce estimates at kitchen tables using spreadsheets or gut instinct. The result:

- Estimates take hours to produce and are often inaccurate
- Invoice payment lag averages 28 days
- Change order disputes are endemic and rarely documented

The first problem — **getting the estimate right, fast** — is what Groundwork solves.

---

## What It Does

1. Contractor opens the app and captures a room (photo or multi-photo)
2. Speaks scope naturally: *"Replace the cabinets, quartz countertops, new flooring"*
3. App uploads media and kicks off an async AI pipeline
4. Contractor receives a line-item estimate broken down by material + labor across Economy / Standard / Premium tiers
5. One tap generates a PDF proposal ready to text or email to the client


https://github.com/user-attachments/assets/03de1435-6099-4185-af45-47e0bd57344e


---

## Architecture

```
┌─────────────────────────────────────────────────┐
│              Mobile App (Expo / React Native)    │
│  Camera → Voice Record → Upload → Poll → Review │
└────────────────────┬────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────┐
│              Flask API (Railway)                 │
│  POST /upload/presign  → S3 presigned URL        │
│  POST /estimate        → enqueue job, return ID  │
│  GET  /estimate/status → poll Celery result      │
│  POST /proposal        → generate PDF            │
│  POST /rooms           → multi-room aggregation  │
│  GET  /projects        → list / get project      │
└──────────┬──────────────────────────┬────────────┘
           │ Celery task              │ read result
           ▼                          ▼
┌────────────────────┐   ┌────────────────────────┐
│  Redis (Railway)   │   │  Redis result cache     │
│  Task broker       │   │  TTL: 24 hr per job     │
└────────┬───────────┘   └────────────────────────┘
         │ consume
         ▼
┌─────────────────────────────────────────────────┐
│              Celery Worker (Railway)             │
│                                                 │
│  Step 1  — Claude Vision (claude-sonnet-4-6)    │
│            Room classification + condition      │
│                                                 │
│  Step 1.5 — Claude (2nd call)                   │
│            Synthesise vision + voice → work     │
│            items list with quantities           │
│                                                 │
│  Step 2  — YOLOv8s (local, on-device)           │
│            Object bounding boxes used as depth  │
│            scale anchors                        │
│                                                 │
│  Step 3  — Depth Anything V2 Small              │
│            Monocular depth map → floor area,    │
│            room dimensions, object scale        │
│                                                 │
│  Step 4  — Quantity Estimator                   │
│            AR measurements → depth map →        │
│            pixel heuristic (priority order)     │
│                                                 │
│  Step 4.5 — Whisper (faster-whisper, local)     │
│             Voice note → transcript             │
│                                                 │
│  Step 5  — Pricing Engine                       │
│            Live HD prices (SerpApi) + RSMeans   │
│            labor tables + ZIP multiplier        │
│            All 3 tiers in one pass              │
│                                                 │
└──────────┬──────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐   ┌────────────────────────┐
│  Supabase (Postgres) │   │  AWS S3                 │
│  projects            │   │  uploads/images/        │
│  room_scans          │   │  uploads/videos/        │
│  estimates           │   │  uploads/audio/         │
│  estimate_line_items │   │  proposals/             │
│  proposals           │   │  preprocessed/          │
│  project_rooms       │   │                         │
└──────────────────────┘   └────────────────────────┘
```

---

## Vision Pipeline Detail

| Step | Model / Service | Purpose |
|------|----------------|---------|
| 1 | Claude Vision (claude-sonnet-4-6) | Classify room type, assess condition, identify features |
| 1.5 | Claude (2nd call) | Synthesise visual features + voice transcript into a definitive work-items list |
| 2 | YOLOv8s (local) | Object bounding boxes — used as depth scale anchors, not primary classification |
| 3 | Depth Anything V2 Small | Monocular depth estimation → floor area (sq ft), room width/depth, per-object real-world dimensions |
| 4 | Quantity Estimator | Merges AR data, depth measurements, and YOLO boxes into quantities per line item |
| 4.5 | faster-whisper (local, `small` model) | Transcribes voice note offline — no Whisper API call |
| 5 | Pricing Engine | SerpApi (Home Depot) for live material prices, RSMeans-calibrated labor tables, regional ZIP multiplier |

---

## Tech Stack

**Mobile**
- Expo SDK 56 / React Native 0.85
- expo-camera, expo-audio, expo-image-picker
- expo-router (file-based navigation)
- Direct-to-S3 upload via presigned PUT URLs

**Backend**
- Flask 3 + Celery 5 + Redis
- Deployed on Railway (API + Worker as separate services)
- Gunicorn (production WSGI)

**AI / ML**
- `anthropic` SDK — Claude Vision classification + scope extraction
- `faster-whisper` — local Whisper STT (no API cost)
- `ultralytics` — YOLOv8s pretrained on COCO (local)
- `transformers` — Depth Anything V2 Small (local)

**Storage**
- Supabase (Postgres + auth)
- AWS S3 (media + proposals)

---

## Design Tradeoffs

### Claude Vision over a fine-tuned classifier
A fine-tuned YOLO classifier would be faster and cheaper at inference time, but requires labeled training data we don't have. Claude understands construction context out of the box — *"oak cabinets, laminate countertops, drop ceiling"* implies a mid-1990s kitchen likely needing full replacement. That nuance is impossible to get from a class label alone. Migrate to a fine-tuned model when enough real estimate data has been collected to train on.

### Local AI models (Whisper, YOLO, Depth Anything) over hosted APIs
Running models locally inside the Celery worker eliminates per-call API costs and network latency. The trade-off is a large Docker image (~2 GB with model weights pre-downloaded) and a slower first build. For the prototype this is the right call — the per-request savings compound quickly.

### Async Celery pipeline over streaming
The vision pipeline takes 8–20 seconds. A blocking HTTP request would time out on mobile and provide no UX feedback. Celery lets the app show a scanning animation while polling for results. The trade-off is polling complexity and an extra Redis dependency.

### Monocular depth over AR measurement
ARKit/ARCore plane detection is highly accurate but requires the user to actively measure. Depth Anything V2 Small produces usable floor-area estimates from a single handheld photo — no user training needed. Accuracy is ±20% vs ±5% for AR, but it works on the first photo a contractor takes without any instruction.

### Two-layer pricing: live HD + hardcoded RSMeans
SerpApi Home Depot queries give live, defensible material prices for the demo. Labor doesn't come from retailers — it comes from trade knowledge. RSMeans-calibrated hourly rates + productivity factors cover the 40–60% of remodel cost that live scraping can't address. Results are cached in Redis for 6 hours to stay within SerpApi quota.

### Supabase over self-managed Postgres
Instant Postgres + auth + REST + realtime subscriptions on a free tier, with no infra to manage during a prototype sprint. The trade-off is a vendor dependency and per-row pricing at scale.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/upload/presign` | Get S3 presigned PUT URL, create room_scan record |
| `POST` | `/estimate` | Enqueue vision pipeline, return `job_id` |
| `GET` | `/estimate/status/:id` | Poll job result |
| `GET` | `/estimates/recent` | List recent estimates |
| `POST` | `/proposal` | Generate PDF proposal from completed estimate |
| `POST` | `/rooms` | Add completed estimate to a project |
| `GET` | `/projects` | List all projects |
| `GET` | `/projects/:id` | Get project with aggregate totals |

---

## Repository Structure

```
groundwork/
├── api/                        # Flask backend
│   ├── app.py                  # Flask app factory
│   ├── celery_worker.py        # Celery entry point
│   ├── config.py               # Environment config
│   ├── Dockerfile
│   ├── docker-compose.yml      # Local dev: Flask + Celery + Redis
│   ├── requirements.txt
│   ├── routes/
│   │   ├── estimate.py
│   │   ├── proposal.py
│   │   ├── rooms.py
│   │   └── upload.py
│   ├── services/
│   │   ├── claude_vision.py    # Room classification + scope extraction
│   │   ├── yolo_detect.py      # Local YOLOv8s detection
│   │   ├── depth_estimator.py  # Depth Anything V2
│   │   ├── whisper_transcribe.py
│   │   ├── pricing_engine.py   # Cost calculation
│   │   ├── serpapi_prices.py   # Live HD pricing
│   │   ├── s3_storage.py
│   │   ├── pdf_generator.py
│   │   ├── quantity_estimator.py
│   │   ├── image_preprocessor.py
│   │   └── video_processor.py
│   ├── tasks/
│   │   ├── vision_pipeline.py  # Main Celery task
│   │   └── proposal_task.py
│   ├── models/
│   │   └── supabase_models.py
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       └── integration/
│
└── groundwork-app/             # Expo React Native app
    └── src/
        ├── app/                # expo-router screens
        │   ├── index.tsx       # Home
        │   ├── camera.tsx      # Camera capture
        │   ├── capture.tsx     # Photo review
        │   ├── scanning.tsx    # Scanning animation + polling
        │   ├── result.tsx      # Detection result + project link
        │   ├── estimate.tsx    # Estimate breakdown
        │   └── proposal.tsx    # PDF proposal
        └── services/
            ├── api.ts          # API client
            ├── upload.ts       # S3 presigned upload
            └── estimateStore.ts
```

---

## Known Limitations

- Quantity estimation without AR is approximate (±20%); single-photo captures miss room features outside the frame
- Depth Anything V2 Small is fast but less accurate than larger depth models or actual AR
- Pricing tables are US national averages — real contractor pricing varies by supplier relationships
- No structural/MEP (mechanical, electrical, plumbing) detection; must be added via voice note
- SerpApi Home Depot queries are rate-limited; falls back to hardcoded RSMeans tables on failure
