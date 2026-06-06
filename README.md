# Painterly
> Upload a photo, get a paint-by-numbers.

---

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [Repository Structure](#repository-structure)
3. [Technology Stack](#technology-stack)
4. [Environment Strategy](#environment-strategy)
5. [Pre-Flight Checklist](#pre-flight-checklist)
6. [Implementation Stories](#implementation-stories)
7. [Secrets & Config Management](#secrets--config-management)
8. [Definition of Done](#definition-of-done)

---

## Architecture Overview

```
  Browser
    │
    ▼
[ Next.js Frontend ]  ──── upload image ────►  [ FastAPI ]
    │                                               │
    │  poll job status                              │  enqueue job
    │◄──────────────────────────────────────────────│
    │                                               ▼
    │                                       [ Redis Queue ]
    │                                               │
    │                                               ▼
    │                                    [ Arq Worker ]
    │                                        │  1. SLIC superpixels
    │                                        │  2. K-Means (LAB, k=10-15)
    │                                        │  3. Region merge
    │                                        │  4. Contour simplification
    │                                        │  5. Number placement
    │                                        │  6. PNG render (300 DPI, 8x10")
    │                                               │
    │                           job done + filename │
    │◄──────────────────────────────────────────────┘
    │
    ▼
[ GET /api/results/{job_id}.png ]  ──► user downloads high-res PNG
```

```
Docker volume: painterly_data
  uploads/   ← original images written by FastAPI
  results/   ← processed PNGs written by worker
```

### Key Design Decisions

- **Shared Docker volume for storage:** For this POC, uploads and results are written to a named Docker volume mounted into both the API and worker containers. No object storage needed — FastAPI serves result files directly.
- **Single Python codebase (FastAPI + Arq worker):** The API and worker share the same `backend/` image and `requirements.txt`. The `pipeline/` package is imported directly by both — no serialization boundary, no language switching.
- **Arq for the job queue:** Python-native async job queue built on Redis. Handles enqueue, status tracking, and retries without a separate runtime.
- **Async job model:** SLIC + K-Means on a large image takes 5–30s. Synchronous HTTP would time out; a poll-based job model lets the frontend show a progress indicator.
- **LAB color space for clustering:** K-Means on LAB (not RGB) produces perceptually uniform color groups — clusters correspond to how humans distinguish colors, which makes the paint palette feel natural.
- **All tunable params as env vars:** Upload size cap, output DPI, output dimensions, color count range, and minimum region area are all environment variables so they can be tuned without code changes.
- **Extensibility mechanism:** New output formats (SVG, PDF, physical kit manifest) are added as worker output adapters configured via `OUTPUT_FORMATS` env var — no API or frontend changes required.

---

## Repository Structure

```
painterly/
├── README.md
├── docker-compose.yml
├── Makefile
├── .env.example                  ← committed; .env is gitignored
│
├── frontend/                     ← Next.js 14 (App Router)
│   ├── Dockerfile
│   ├── public/
│   │   └── .gitkeep
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              ← upload UI + job polling
│   │   └── result/[jobId]/
│   │       └── page.tsx          ← preview + download
│   └── components/
│       ├── Uploader.tsx
│       ├── ColorLegend.tsx
│       └── JobStatus.tsx
│
└── backend/                      ← Python 3.12 (FastAPI + Arq worker)
    ├── Dockerfile
    ├── requirements.txt
    ├── api/
    │   ├── main.py               ← FastAPI app + route registration
    │   └── routes/
    │       ├── upload.py         ← POST /api/upload: validate, save to volume, enqueue
    │       ├── jobs.py           ← GET /api/jobs/{id}: status
    │       └── results.py        ← GET /api/results/{job_id}.png: file download
    ├── worker/
    │   ├── main.py               ← Arq WorkerSettings + job function
    │   └── tasks.py              ← process_image: read upload → pipeline → write result
    └── pipeline/
        ├── __init__.py
        ├── superpixels.py        ← SLIC via scikit-image
        ├── clustering.py         ← K-Means in LAB space
        ├── regions.py            ← merge small regions, contour simplification
        ├── numbering.py          ← centroid placement, leader lines
        ├── render.py             ← final PNG at target DPI/size
        └── palette.py            ← Apple Barrel color map + nearest-match
```

---

## Technology Stack

| Layer | Technology | Reason |
|---|---|---|
| Frontend | Next.js 14 (App Router) | SSR + easy polling with server actions |
| Styling | Tailwind CSS | Rapid UI, consistent design tokens |
| Backend API | Python 3.12 + FastAPI | Same language as the pipeline; shared code, one Dockerfile |
| Job Queue | Arq + Redis | Python-native async queue; no separate runtime |
| Image Processing | scikit-image + OpenCV + scikit-learn | SLIC, K-Means, and contour ops are Python-native |
| File Storage | Docker named volume (local) / Fly Volume (prod) | Simple, no external dependencies; persists across deploys on Fly |
| Proxy | Caddy 2 | Simple local reverse proxy; Automatic HTTPS when needed |
| Containers | Docker + Compose | Consistent across envs |
| Hosting | Fly.io (process groups) | Docker-native, scale-to-zero, Fly Volumes for persistence |
| DNS | Namecheap → Fly.io | CNAME `paint.brandonlocke.xyz` → Fly app |
| CI/CD | GitHub Actions | Build → `fly deploy` on merge to `main` |

---

## Environment Strategy

| | Local | Production |
|---|---|---|
| Domain | `localhost` | `paint.brandonlocke.xyz` |
| TLS | none | Fly.io (automatic) |
| Secrets | `.env` file | `fly secrets set` |
| Deploy | `make dev` | `fly deploy` (GitHub Actions) |

---

## Pre-Flight Checklist

Run before first `docker compose build` and after any environment change:

```bash
# Docker is running
docker info > /dev/null && echo "✓ Docker running" || echo "✗ Docker not running"

# DNS works from Docker (if this fails, restart Docker daemon)
docker run --rm alpine nslookup registry-1.docker.io && echo "✓ Docker DNS ok"

# Required ports are free
lsof -i :80 -i :3000 -i :8000 -i :6379 | grep LISTEN && echo "⚠ ports in use" || echo "✓ ports free"

# .env exists
test -f .env && echo "✓ .env found" || echo "✗ copy .env.example to .env"
```

If Docker DNS fails: `sudo systemctl restart docker` then re-run.

> **Ctrl+C not responding?** If `docker compose up` hangs on stop, your services are missing `stop_grace_period`. All services in `docker-compose.yml` should have `stop_grace_period: 5s`.

---

## Implementation Stories

### Epic 1 — Core Pipeline (Local, No UI)

#### Story 1.1 — Backend skeleton + SLIC superpixels

**Context:** Nothing exists yet. This story establishes the `backend/` service and validates that SLIC superpixel segmentation runs correctly on a test image.

**Assumptions:**
- Docker and Docker Compose are installed
- `.env` copied from `.env.example`
- A sample test image (`backend/test_assets/sample.jpg`) committed to the repo

**Tasks:**
- Scaffold `backend/` directory structure as specified in repo layout
- Create `requirements.txt`: `fastapi`, `uvicorn[standard]`, `arq`, `scikit-image`, `opencv-python-headless`, `scikit-learn`, `numpy`, `Pillow`, `python-multipart`, `ruff`
- Implement `pipeline/superpixels.py`: `run_slic(image_array, n_segments, compactness) -> label_array`
  - Accept `n_segments` and `compactness` from env vars `SLIC_N_SEGMENTS` (default 1000) and `SLIC_COMPACTNESS` (default 10)
  - Work in LAB color space internally
- Implement a standalone `pipeline/debug.py` script that loads `test_assets/sample.jpg`, runs SLIC, and saves a labeled overlay PNG to `test_assets/output_slic.png`
- Create `backend/Dockerfile` (Python 3.12-slim base; default `CMD` runs the API via uvicorn; worker invoked via command override)
- Add `backend` service to `docker-compose.yml` with `command: python pipeline/debug.py` for this story

**Out of Scope:** Clustering, region merging, number placement, FastAPI routes, Redis.

**Acceptance Criteria:**
- [ ] `docker compose run backend python pipeline/debug.py` exits 0
- [ ] `test_assets/output_slic.png` is written and visually shows superpixel boundaries
- [ ] `SLIC_N_SEGMENTS` env var changes the segment count when re-run

---

#### Story 1.2 — K-Means color clustering in LAB space

**Context:** Story 1.1 complete. SLIC produces a `label_array`. This story maps every superpixel to one of k palette colors using K-Means in LAB space.

**Assumptions:**
- `pipeline/superpixels.py` exists and returns a valid `label_array`
- `PALETTE_K` env var available (default 12, range 10–15)

**Tasks:**
- Implement `pipeline/clustering.py`:
  - `compute_superpixel_means(image_lab, label_array) -> (superpixel_ids, mean_colors_lab)`
  - `cluster_colors(mean_colors_lab, k) -> (cluster_labels, centroids_lab)`
  - `assign_superpixels(label_array, superpixel_ids, cluster_labels) -> region_map` (same shape as label_array, values are 0..k-1)
- Implement `pipeline/palette.py`:
  - Hard-code Apple Barrel acrylic paint colors (name + RGB) as a lookup table
  - `match_palette(centroids_lab) -> list[AppleBarrelColor]` — nearest LAB match for each centroid
- Update `debug.py` to run clustering after SLIC and save a flat-color preview PNG (`output_clustered.png`)

**Out of Scope:** Region merging, contour extraction, numbering, API routes, UI.

**Acceptance Criteria:**
- [ ] `output_clustered.png` renders the image using exactly k flat colors
- [ ] Changing `PALETTE_K` to 10 vs 15 visibly changes color count
- [ ] Each cluster is matched to a named Apple Barrel color (printed to stdout in debug mode)

---

#### Story 1.3 — Region merging and contour simplification

**Context:** Stories 1.1–1.2 complete. We have a `region_map` with k color labels. This story cleans up the map and extracts paintable region boundaries.

**Assumptions:**
- `pipeline/clustering.py` returns a valid `region_map`
- `MIN_REGION_PX` env var available (default 200)

**Tasks:**
- Implement `pipeline/regions.py`:
  - `merge_small_regions(region_map, min_px) -> region_map` — absorb regions smaller than `MIN_REGION_PX` into their largest neighbor by color label
  - `extract_contours(region_map) -> list[Contour]` — use OpenCV `findContours` on per-label binary masks
  - `simplify_contours(contours, epsilon_factor=0.002) -> list[Contour]` — Ramer-Douglas-Peucker via `cv2.approxPolyDP`; `epsilon = epsilon_factor * arc_length`
- Update `debug.py` to run the full pipeline through contour extraction and save `output_contours.png` (black contours on white background)

**Out of Scope:** Number placement, final render, API routes, UI.

**Acceptance Criteria:**
- [ ] `output_contours.png` has clean, non-jagged region outlines
- [ ] No region in the output is smaller than `MIN_REGION_PX` pixels
- [ ] Lowering `MIN_REGION_PX` to 0 produces more (smaller) regions; raising it to 2000 noticeably simplifies

---

#### Story 1.4 — Number placement and final PNG render

**Context:** Stories 1.1–1.3 complete. Clean contours exist. This story places region numbers and renders the final high-res paint-by-numbers PNG.

**Assumptions:**
- `pipeline/regions.py` returns simplified contours and a clean `region_map`
- `OUTPUT_DPI` (default 300), `OUTPUT_WIDTH_IN` (default 8), `OUTPUT_HEIGHT_IN` (default 10) env vars available

**Tasks:**
- Implement `pipeline/numbering.py`:
  - `place_numbers(region_map, region_labels) -> list[NumberPlacement]` — compute centroid of each region; if centroid falls inside the region, place number there; otherwise find the largest inscribed point via distance transform
  - Regions with area < `MIN_LABEL_PX` (env var, default 500) are unlabeled
- Implement `pipeline/render.py`:
  - `render_png(contours, number_placements, palette_colors, output_path)` — produce final PNG at `OUTPUT_DPI × OUTPUT_WIDTH_IN` by `OUTPUT_DPI × OUTPUT_HEIGHT_IN` pixels
  - White background, black contours (1–2px), numbers in a clean serif font sized proportionally to region area
  - Color legend strip along the bottom: swatch + number + Apple Barrel paint name
- Update `debug.py` to run the full pipeline end-to-end and write `output_final.png`

**Out of Scope:** API routes, job queue, UI.

**Acceptance Criteria:**
- [ ] `output_final.png` is exactly `OUTPUT_DPI * OUTPUT_WIDTH_IN` × `OUTPUT_DPI * OUTPUT_HEIGHT_IN` pixels
- [ ] Every labeled region has a readable number that does not overlap a contour line
- [ ] Color legend at the bottom shows all k colors with names
- [ ] Running on 3 visually different test images (portrait, landscape, object) all produce sensible output

---

### Epic 2 — API + Job Queue

#### Story 2.1 — FastAPI upload endpoint + Arq job enqueue

**Context:** Epic 1 complete; the Python pipeline works end-to-end. This story adds the FastAPI routes and wires upload → volume → Arq job enqueue.

**Assumptions:**
- Named Docker volume `painterly_data` defined in `docker-compose.yml` and mounted at `DATA_DIR` (default `/data`) in both `api` and `worker` containers
- `MAX_UPLOAD_BYTES` env var set (default `20971520` = 20 MB)
- Redis running as a Docker service

**Tasks:**
- Implement `api/main.py`: FastAPI app with lifespan context manager; include routers
- Implement `api/routes/upload.py`:
  - `POST /api/upload` — validate content type (JPEG/PNG only), enforce `MAX_UPLOAD_BYTES`, write file to `$DATA_DIR/uploads/{job_id}.{ext}`, enqueue Arq job with `job_id` and `palette_k`
  - Return `{"job_id": "..."}` to client
- Implement `api/routes/results.py`:
  - `GET /api/results/{job_id}.png` — stream file from `$DATA_DIR/results/{job_id}.png`; return 404 if not found
- Add `redis` service and `painterly_data` named volume to `docker-compose.yml`
- Update `backend` service default command to `uvicorn api.main:app --host 0.0.0.0 --port 8000`

**Out of Scope:** Job status endpoint, worker integration, frontend.

**Acceptance Criteria:**
- [ ] `curl -F "file=@sample.jpg" http://localhost:8000/api/upload` returns `{"job_id": "..."}` within 2s
- [ ] File appears in the Docker volume under `uploads/`
- [ ] Job appears in Arq queue (`redis-cli LLEN arq:queue`)
- [ ] File > `MAX_UPLOAD_BYTES` returns 413
- [ ] Non-image file returns 415

---

#### Story 2.2 — FastAPI job status endpoint

**Context:** Story 2.1 complete. Jobs are enqueued. This story adds the status endpoint the frontend will poll.

**Tasks:**
- Implement `api/routes/jobs.py`:
  - `GET /api/jobs/{id}` — query Arq job status from Redis; return `{"status": "pending"|"in_progress"|"complete"|"not_found"|"failed", "download_url"?: str}`
  - On `complete`: include `download_url` as `/api/results/{job_id}.png`
- Write an integration test: enqueue a fake Arq job, assert endpoint returns `pending`; simulate completion, assert it returns `complete` + correct `download_url`

**Out of Scope:** Worker integration, frontend.

**Acceptance Criteria:**
- [ ] `GET /api/jobs/{id}` returns `pending` for a newly enqueued job
- [ ] After simulating job completion in Redis, returns `complete` with a `download_url`
- [ ] `GET` on that `download_url` returns the file (place a dummy PNG in the volume to test)

---

#### Story 2.3 — Arq worker: job processing integration

**Context:** Stories 2.1–2.2 complete. The API enqueues jobs; the pipeline runs locally. This story connects the worker to Redis and the shared volume so it processes jobs end-to-end.

**Assumptions:**
- `painterly_data` volume mounted at `DATA_DIR` in the worker container (same path as API)
- `REDIS_URL` env var available

**Tasks:**
- Implement `worker/tasks.py`:
  - `async def process_image(ctx, job_id, palette_k)`:
    - Read upload from `$DATA_DIR/uploads/{job_id}.*` (glob for extension)
    - Run full pipeline (`superpixels → clustering → regions → numbering → render`)
    - Write result PNG to `$DATA_DIR/results/{job_id}.png`
    - On exception: re-raise so Arq marks job as failed
- Implement `worker/main.py`: `WorkerSettings` with `functions=[process_image]`, Redis pool from `REDIS_URL`
- Add `worker` service to `docker-compose.yml`: same image as `backend`, command override `python -m arq worker.main.WorkerSettings`, same volume mount

**Out of Scope:** Frontend, retries/dead-letter queue.

**Acceptance Criteria:**
- [ ] `docker compose up` — all services (api, worker, redis) stay running
- [ ] `curl -F "file=@sample.jpg" http://localhost:8000/api/upload` → poll `/api/jobs/{id}` → status eventually becomes `complete`
- [ ] `curl http://localhost:8000/api/results/{job_id}.png --output result.png` downloads a valid paint-by-numbers PNG
- [ ] Uploading a corrupt file results in job status `failed`

---

### Epic 3 — Frontend

#### Story 3.1 — Upload UI with job polling

**Context:** Epic 2 complete. The API accepts uploads and returns job status. This story builds the frontend upload flow.

**Assumptions:**
- `NEXT_PUBLIC_API_URL` env var points to the FastAPI backend
- Next.js 14 app scaffolded in `frontend/`

**Tasks:**
- Implement `components/Uploader.tsx`: drag-and-drop + click-to-browse; client-side file type and size validation (read limit from `NEXT_PUBLIC_MAX_UPLOAD_MB` env var)
- Implement `app/page.tsx`: upload form → `POST /api/upload` → begin polling `GET /api/jobs/{id}` every 2s
- Implement `components/JobStatus.tsx`: progress states — idle, uploading, processing (with elapsed timer), complete, error
- On `complete`: redirect to `/result/[jobId]`
- Implement `app/result/[jobId]/page.tsx`: call `GET /api/jobs/{id}` for `download_url`, show preview image, "Download PNG" button, color legend (`components/ColorLegend.tsx` — numbered swatches with Apple Barrel paint names)

**Out of Scope:** Auth, purchase flow, responsive mobile polish.

**Acceptance Criteria:**
- [ ] Upload a JPEG → see processing state → result page loads with preview
- [ ] Download button fetches the actual PNG file
- [ ] Uploading a file over the size limit shows a client-side error before any network request
- [ ] Color legend matches the k colors in the downloaded PNG

---

#### Story 3.2 — Color count selector + polish

**Context:** Story 3.1 complete. End-to-end flow works. This story adds the color count control and general UI polish.

**Assumptions:**
- `NEXT_PUBLIC_PALETTE_K_MIN` (default 10) and `NEXT_PUBLIC_PALETTE_K_MAX` (default 15) env vars available

**Tasks:**
- Add a segmented control or slider to the upload UI: "Number of colors" (10–15); pass selected `k` to `POST /api/upload` body
- Add responsive layout for mobile viewports
- Add loading skeleton on result page while status is polled
- Error boundary: if job fails, show friendly message + "Try another photo" CTA

**Out of Scope:** Purchase flow, user accounts, saving past results.

**Acceptance Criteria:**
- [ ] Selecting 10 vs 15 colors produces visually different outputs
- [ ] UI is usable on a 390px-wide viewport
- [ ] Error state is shown when worker returns a failed job status

---

### Epic 4 — Production Deployment

#### Story 4.1 — Fly.io app + volume setup

**Context:** Epics 1–3 complete. Full local stack works. This story provisions the Fly.io app, creates the persistent volume, and validates that the backend can read/write files from it in production.

**Assumptions:**
- `flyctl` installed and authenticated (`fly auth login`)
- GitHub repo exists; `FLY_API_TOKEN` secret added to GitHub repo settings
- A single Fly app will use [process groups](https://fly.io/docs/apps/processes/) to run `api`, `worker`, and `redis` as separate processes under one `fly.toml`

**Tasks:**
- Run `fly launch --no-deploy` to scaffold the app named `painterly`; save the generated `fly.toml` to the repo root
- Configure `fly.toml` process groups:
  ```toml
  [processes]
    api    = "uvicorn api.main:app --host 0.0.0.0 --port 8000"
    worker = "python -m arq worker.main.WorkerSettings"
    redis  = "redis-server --save 60 1 --loglevel warning"
  ```
- Configure scale-to-zero for `api` and `worker` processes:
  ```toml
  [[services]]
    processes = ["api"]
    [services.concurrency]
      type       = "requests"
      soft_limit = 10
      hard_limit = 25
  
  [http_service]
    min_machines_running = 0   # scale to zero when idle
    auto_stop_machines   = true
    auto_start_machines  = true
  ```
- Set `redis` process to `min_machines_running = 1` (Redis must stay up to hold queue state; it's cheap at 256 MB)
- Create Fly Volume:
  ```bash
  fly volumes create painterly_data --size 5 --region iad
  ```
- Mount the volume in `fly.toml`:
  ```toml
  [mounts]
    source      = "painterly_data"
    destination = "/data"
    processes   = ["api", "worker"]
  ```
- Add `uploads/` and `results/` directory creation to app startup (both API and worker should `mkdir -p $DATA_DIR/uploads $DATA_DIR/results` on init)
- Set all production secrets:
  ```bash
  fly secrets set \
    REDIS_URL=redis://localhost:6379 \
    DATA_DIR=/data \
    MAX_UPLOAD_BYTES=20971520 \
    OUTPUT_DPI=300 \
    OUTPUT_WIDTH_IN=8 \
    OUTPUT_HEIGHT_IN=10 \
    SLIC_N_SEGMENTS=1000 \
    SLIC_COMPACTNESS=10 \
    PALETTE_K=12 \
    MIN_REGION_PX=200 \
    MIN_LABEL_PX=500 \
    NEXT_PUBLIC_API_URL=https://paint.brandonlocke.xyz \
    NEXT_PUBLIC_MAX_UPLOAD_MB=20 \
    NEXT_PUBLIC_PALETTE_K_MIN=10 \
    NEXT_PUBLIC_PALETTE_K_MAX=15
  ```
- Run `fly deploy` manually for this first story to validate the config

**Out of Scope:** Custom domain, GitHub Actions CI/CD.

**Acceptance Criteria:**
- [ ] `fly deploy` completes without error; all three process groups show `running` in `fly status`
- [ ] `fly ssh console -s api` → `ls /data` shows `uploads/` and `results/` directories
- [ ] `curl https://painterly.fly.dev/api/upload -F "file=@sample.jpg"` returns `{"job_id": "..."}` 
- [ ] Polling `/api/jobs/{id}` eventually returns `complete` and the result PNG is downloadable
- [ ] `fly scale show` confirms `min_machines_running = 0` for api and worker processes

---

#### Story 4.2 — Custom domain (Namecheap → Fly.io)

**Context:** Story 4.1 complete. App is live at `painterly.fly.dev`. This story points `paint.brandonlocke.xyz` at it.

**Assumptions:**
- `brandonlocke.xyz` is registered and managed in Namecheap
- Access to Namecheap Advanced DNS settings

**Tasks:**
- Add the custom domain to Fly:
  ```bash
  fly certs add paint.brandonlocke.xyz
  fly certs show paint.brandonlocke.xyz   # note the CNAME target
  ```
- In Namecheap Advanced DNS, add a CNAME record:
  | Type | Host | Value | TTL |
  |---|---|---|---|
  | CNAME | `paint` | `painterly.fly.dev.` (trailing dot) | Automatic |
- Wait for DNS propagation (typically 5–30 min); verify with `dig paint.brandonlocke.xyz`
- Fly auto-provisions TLS via Let's Encrypt once DNS resolves — confirm with `fly certs show paint.brandonlocke.xyz` (status should be `Issued`)
- Update `NEXT_PUBLIC_API_URL` secret to `https://paint.brandonlocke.xyz`:
  ```bash
  fly secrets set NEXT_PUBLIC_API_URL=https://paint.brandonlocke.xyz
  fly deploy
  ```

> **Note:** If Namecheap's DNS is proxied through anything, disable it — Fly manages TLS directly and needs a bare CNAME.

**Out of Scope:** GitHub Actions CI/CD.

**Acceptance Criteria:**
- [ ] `https://paint.brandonlocke.xyz` loads the frontend with a valid TLS cert
- [ ] Full upload → process → download flow works on the custom domain
- [ ] `fly certs show paint.brandonlocke.xyz` shows `Issued` (not `Awaiting`)

---

#### Story 4.3 — GitHub Actions CI/CD

**Context:** Stories 4.1–4.2 complete. App is live on the custom domain. This story automates deploys on merge to `main`.

**Assumptions:**
- `FLY_API_TOKEN` secret set in GitHub repo settings (`fly tokens create deploy` to generate)
- Repo has a `main` branch that is the source of truth for production

**Tasks:**
- Create `.github/workflows/deploy.yml`:
  ```yaml
  name: Deploy
  on:
    push:
      branches: [main]
  jobs:
    lint-python:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: { python-version: "3.12" }
        - run: pip install ruff && ruff check backend/
    lint-frontend:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-node@v4
          with: { node-version: "20" }
        - run: cd frontend && npm ci && npm run lint
    deploy:
      needs: [lint-python, lint-frontend]
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: superfly/flyctl-actions/setup-flyctl@master
        - run: fly deploy --remote-only
          env:
            FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
  ```
- Add `Makefile` targets:
  ```makefile
  dev:
      docker compose up --build
  
  logs:
      docker compose logs -f
  
  ps:
      docker compose ps
  
  deploy:
      fly deploy --remote-only
  ```

**Out of Scope:** Staging environment, rollback automation, Slack notifications.

**Acceptance Criteria:**
- [ ] Push a trivial change to `main` → GitHub Actions runs → lint passes → `fly deploy` succeeds
- [ ] A linting error in `backend/` blocks the deploy (lint job fails, deploy job is skipped)
- [ ] `https://paint.brandonlocke.xyz` reflects the new deploy within ~5 minutes of the push

---

## Secrets & Config Management

All configuration lives in `.env` (local) or Fly.io secrets (production). Never commit `.env`.

```bash
# .env.example

# --- Upload limits ---
MAX_UPLOAD_BYTES=20971520        # 20 MB

# --- File storage ---
DATA_DIR=/data                   # Docker volume mount point (local: painterly_data, prod: Fly Volume)

# --- Output dimensions ---
OUTPUT_DPI=300
OUTPUT_WIDTH_IN=8
OUTPUT_HEIGHT_IN=10

# --- Pipeline tuning ---
SLIC_N_SEGMENTS=1000
SLIC_COMPACTNESS=10
PALETTE_K=12
MIN_REGION_PX=200
MIN_LABEL_PX=500

# --- Infrastructure ---
REDIS_URL=redis://redis:6379     # local: Docker service; prod: localhost (same Fly VM)

# --- Frontend (public) ---
NEXT_PUBLIC_API_URL=http://localhost:8000   # prod: https://paint.brandonlocke.xyz
NEXT_PUBLIC_MAX_UPLOAD_MB=20
NEXT_PUBLIC_PALETTE_K_MIN=10
NEXT_PUBLIC_PALETTE_K_MAX=15
```

### Production secrets reference

```bash
# Run once to set all prod secrets (update values as needed)
fly secrets set \
  REDIS_URL=redis://localhost:6379 \
  DATA_DIR=/data \
  MAX_UPLOAD_BYTES=20971520 \
  OUTPUT_DPI=300 \
  OUTPUT_WIDTH_IN=8 \
  OUTPUT_HEIGHT_IN=10 \
  SLIC_N_SEGMENTS=1000 \
  SLIC_COMPACTNESS=10 \
  PALETTE_K=12 \
  MIN_REGION_PX=200 \
  MIN_LABEL_PX=500 \
  NEXT_PUBLIC_API_URL=https://paint.brandonlocke.xyz \
  NEXT_PUBLIC_MAX_UPLOAD_MB=20 \
  NEXT_PUBLIC_PALETTE_K_MIN=10 \
  NEXT_PUBLIC_PALETTE_K_MAX=15
```

---

## Definition of Done

A story is done when:
- [ ] All acceptance criteria are checked
- [ ] `docker compose up` — all containers stay healthy for 60s with no restarts (Epics 1–3)
- [ ] No secrets committed; all config follows the `.env` / `fly secrets` pattern
- [ ] New env vars added to `.env.example` with defaults and a comment
- [ ] Code is linted (`ruff` for Python, `eslint` for Next.js)
- [ ] Any new pipeline parameter is an env var, not a hardcode
