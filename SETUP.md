# Setup Guide

## Prerequisites

- Node.js 20+ and npm
- Python 3.12+
- Docker Desktop (for local backend dev)
- Expo CLI: `npm install -g expo-cli`
- EAS CLI: `npm install -g eas-cli` (for device builds)
- An AWS account with S3 access
- A Supabase project
- Accounts / API keys for: Anthropic, SerpApi

---

## Backend — Local Development

### 1. Clone and configure environment

```bash
git clone https://github.com/RAAHUL-tech/groundwork.git
cd groundwork/api
cp .env.example .env
```

Fill in `api/.env`:

```bash
# AI APIs
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...          # optional — only used as Claude fallback
SERPAPI_KEY=...

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_JWT_SECRET=...        # from Supabase → Settings → API → JWT Secret

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=groundwork-uploads
S3_REGION=us-west-2

# Redis (local Docker)
REDIS_URL=redis://localhost:6379/0

# App
FLASK_ENV=development
DEV_PROJECT_ID=<uuid-from-supabase-projects-table>
```

### 2. Set up Supabase tables

In your Supabase project → SQL Editor, run:

```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES auth.users,
  name TEXT NOT NULL,
  client_name TEXT,
  client_address TEXT,
  status TEXT DEFAULT 'active',
  total_estimate NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE room_scans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects,
  room_label TEXT,
  room_type TEXT,
  room_confidence NUMERIC,
  condition TEXT,
  image_urls TEXT[],
  video_url TEXT,
  voice_transcript TEXT,
  celery_job_id TEXT,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE estimates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_scan_id UUID REFERENCES room_scans,
  project_id UUID REFERENCES projects,
  tier TEXT DEFAULT 'standard',
  subtotal_materials NUMERIC,
  subtotal_labor NUMERIC,
  permits NUMERIC,
  contingency NUMERIC,
  total_estimate NUMERIC,
  estimate_low NUMERIC,
  estimate_high NUMERIC,
  confidence_score NUMERIC,
  confidence_label TEXT,
  regional_multiplier NUMERIC,
  scope_narrative TEXT,
  timeline_weeks INTEGER,
  raw_response JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE estimate_line_items (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  estimate_id UUID REFERENCES estimates,
  item_label TEXT,
  scope_description TEXT,
  quantity NUMERIC,
  unit TEXT,
  material_unit_cost NUMERIC,
  labor_unit_cost NUMERIC,
  total NUMERIC,
  hd_price_reference TEXT,
  source TEXT,
  detection_confidence NUMERIC
);

CREATE TABLE proposals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects,
  estimate_id UUID REFERENCES estimates,
  pdf_url TEXT,
  contractor_snapshot JSONB,
  client_snapshot JSONB,
  payment_terms TEXT,
  valid_until DATE,
  sent_at TIMESTAMPTZ,
  status TEXT DEFAULT 'draft',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE project_rooms (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  room_scan_id UUID REFERENCES room_scans(id) ON DELETE SET NULL,
  estimate_id UUID REFERENCES estimates(id) ON DELETE SET NULL,
  room_label TEXT NOT NULL,
  total_estimate NUMERIC NOT NULL DEFAULT 0,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, room_scan_id)
);
CREATE INDEX idx_project_rooms_project_id ON project_rooms (project_id);
```

Also create a default project and note its UUID for `DEV_PROJECT_ID`:

```sql
INSERT INTO projects (name, client_name, status)
VALUES ('Dev Project', 'Test Homeowner', 'active')
RETURNING id;
```

### 3. Create an S3 bucket

```bash
aws s3 mb s3://groundwork-uploads --region us-west-2
```

Add a bucket policy to allow presigned PUT uploads (CORS):

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["PUT", "GET"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```

### 4. Start with Docker Compose

```bash
cd groundwork/api
docker compose up --build
```

This starts:
- `groundwork_api` — Flask on port `5001`
- `groundwork_worker` — Celery worker (loads YOLOv8s + Whisper + Depth model on first start — ~2 min)
- `groundwork_redis` — Redis on port `6379`

Verify:
```bash
curl http://localhost:5001/health
# → {"status": "ok", "service": "groundwork-api"}
```

### 5. Run the test suite

```bash
cd groundwork/api
python3 -m pytest tests/ -q
# 245 passed
```

---

## Backend — Deploy to Railway

### Services to create

You need **3 Railway services** in one project:

| Service | Type | Source |
|---------|------|--------|
| Redis | Database → Redis | Railway managed |
| groundworks-api | GitHub repo | `api/` directory |
| clery-worker | GitHub repo | `api/` directory |

### Steps

**1. Create Redis**
- New Service → Database → Redis
- Note: Railway auto-generates `REDIS_URL` (with password)

**2. Deploy API service**
- New Service → GitHub Repo → select repo
- Settings → Build → Root Directory: `api`
- Settings → Start Command: *(leave blank — uses Dockerfile CMD)*
- Settings → Networking → Generate Domain (Railway assigns port via `$PORT`)

**3. Deploy Celery worker**
- New Service → GitHub Repo → same repo
- Settings → Build → Root Directory: `api`
- Settings → Start Command: `celery -A celery_worker worker --loglevel=info --concurrency=2`
- No networking needed

**4. Set environment variables**

In both `groundworks-api` and `clery-worker` → Variables → Raw Editor:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
SERPAPI_KEY=...
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
SUPABASE_JWT_SECRET=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=groundwork-uploads
S3_REGION=us-west-2
FLASK_ENV=production
DEV_PROJECT_ID=<uuid>
```

For `REDIS_URL` — use a Railway reference variable (not a hardcoded URL):
- Add Variable → Name: `REDIS_URL` → Value: `${{Redis.REDIS_URL}}`

**5. Deploy**

Trigger a deploy on both services. First deploy takes ~10 minutes (downloads AI model weights during Docker build). Subsequent deploys use cached layers.

Verify:
```bash
curl https://your-api.railway.app/health
# → {"status": "ok", "service": "groundwork-api"}
```

---

## Mobile App — Local Development

### 1. Configure environment

```bash
cd groundwork/groundwork-app
```

Create `.env` in `groundwork-app/`:
```bash
# Point to your local backend
EXPO_PUBLIC_API_URL=http://<your-local-ip>:5001

# For production Railway backend:
# EXPO_PUBLIC_API_URL=https://your-api.railway.app
```

Find your local IP:
```bash
# macOS
ipconfig getifaddr en0
```

### 2. Install dependencies

```bash
npm install
```

### 3. Run on simulator

```bash
# iOS Simulator (macOS only)
npx expo run:ios

# Android Emulator
npx expo run:android
```

### 4. Run on physical device (Expo Go)

```bash
npx expo start
```

Scan the QR code with:
- iOS: Camera app
- Android: Expo Go app

> **Note:** Physical device and your backend must be on the same WiFi network for local development.

---

## Mobile App — Build for iOS (TestFlight / App Store)

### Prerequisites

- Apple Developer account ($99/yr)
- Xcode installed (macOS only)
- `eas login` with your Expo account

### Build

```bash
cd groundwork/groundwork-app

# Development build (for testing on device without App Store)
eas build --platform ios --profile development

# Production build (for TestFlight / App Store)
eas build --platform ios --profile production
```

EAS builds in the cloud — no Mac with Xcode required for production builds.

### Submit to TestFlight

```bash
eas submit --platform ios --latest
```

Then in App Store Connect → TestFlight → add testers.

### App identifiers

- Bundle ID: `com.rahulkrish28.groundwork-app`
- Configured in `groundwork-app/app.json` under `expo.ios.bundleIdentifier`

---

## Mobile App — Build for Android

### Prerequisites

- Google Play Developer account ($25 one-time)
- `eas login` with your Expo account

### Build

```bash
cd groundwork/groundwork-app

# APK for direct install / internal testing
eas build --platform android --profile preview

# AAB for Play Store
eas build --platform android --profile production
```

### Submit to Play Store

```bash
eas submit --platform android --latest
```

Or download the `.aab` from EAS and upload manually in Google Play Console → Internal Testing.

### Permissions

The app requests:
- `CAMERA` — room capture
- `RECORD_AUDIO` — voice scope notes
- `MODIFY_AUDIO_SETTINGS` — audio routing during recording

Configured in `groundwork-app/app.json` under `expo.android.permissions`.

---

## Environment Variables Reference

### Backend (`api/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude Vision + scope extraction |
| `OPENAI_API_KEY` | No | GPT-4o fallback if Claude is unavailable |
| `SERPAPI_KEY` | No | Live Home Depot prices (falls back to hardcoded tables) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key (bypasses RLS) |
| `SUPABASE_JWT_SECRET` | Yes | For verifying user JWTs |
| `AWS_ACCESS_KEY_ID` | Yes | S3 uploads |
| `AWS_SECRET_ACCESS_KEY` | Yes | S3 uploads |
| `S3_BUCKET` | Yes | Bucket name |
| `S3_REGION` | Yes | Bucket region |
| `REDIS_URL` | Yes | Celery broker + result cache |
| `FLASK_ENV` | No | `development` or `production` |
| `DEV_PROJECT_ID` | No | Default project UUID used when no auth token is present |

### Mobile (`groundwork-app/.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `EXPO_PUBLIC_API_URL` | Yes | Base URL of the Flask API |
