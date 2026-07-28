# FocusStream — Backend

Intent-driven content curation. Users define **Intent Sprints** (learning goals);
the backend ingests content, embeds it, matches it against active sprints by
semantic similarity, synthesizes a tailored takeaway for high-signal matches, and
serves pre-computed **Signal Cards** to the feed.

## Stack

- **FastAPI** (async) — REST API
- **PostgreSQL 16 + pgvector** — relational store + vector search
- **Redis + Celery** (worker + beat) — async ingestion / embedding / matching / synthesis
- **OpenAI `text-embedding-3-large`** — embeddings (truncated to 1536 dims)
- **Claude Sonnet** — 1-sentence takeaway synthesis

## Architecture

```
Client ──> FastAPI ──> Postgres (+pgvector)      [request path: pure DB reads]
                │
                └── dispatch ──> Redis ──> Celery worker
                                            embed ─> match (cosine) ─> synthesize ─> Signal Card
```

The request path never touches the embedding model or the LLM. All AI work is
async and pre-computed, so `GET /feed` is a fast join over `signal_cards`.

## Run it

```bash
cp .env.example .env      # then fill in OPENAI_API_KEY and ANTHROPIC_API_KEY
docker compose up --build
```

This starts Postgres (pgvector image), Redis, the API (runs `alembic upgrade head`
on boot), a Celery worker, and Celery beat.

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/sprints` | Create an Intent Sprint (+ dispatch async embedding) |
| `GET`  | `/api/v1/sprints/{sprint_id}/feed` | Signal feed, ordered by score then recency |
| `POST` | `/api/v1/feedback` | Record upvote / downvote / save / dismiss |

### Try it

```bash
# (create a user first — no signup endpoint in this slice)
docker compose exec db psql -U focusstream -c \
  "INSERT INTO users (id, email) VALUES ('usr_9921', 'demo@focusstream.app');"

curl -X POST http://localhost:8000/api/v1/sprints \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"usr_9921","title":"Prepare for AI Compliance Audit",
       "description":"EU AI Act guidelines, compliance checklists, SaaS penalties.",
       "duration_days":14,"sources_allowed":["rss","newsletters","podcasts"]}'
```

## Deploy (Render)

This is a **backend** — it can't run on static hosting (GitHub Pages, etc.); it
needs a server runtime plus Postgres and Redis. [`render.yaml`](render.yaml) is a
Render Blueprint that provisions the whole stack.

1. Push this repo to GitHub.
2. Render → **New → Blueprint** → pick the repo. It reads `render.yaml` and
   creates: `focusstream-api` (web), `focusstream-worker`, `focusstream-beat`,
   `focusstream-db` (Postgres + pgvector), `focusstream-redis`.
3. When prompted, set the secrets: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.
4. First deploy runs `alembic upgrade head` automatically (creates the `vector`
   extension + schema). To seed demo data, open the web service's **Shell** and
   run `python -m app.scripts.seed`.

The API is then live at `https://focusstream-api.onrender.com` (`/docs` for
Swagger). Point the mobile app's `API_BASE_URL` at it, and set
`CORS_ALLOW_ORIGINS` to the app's web origin for production.

> Background workers aren't free-tier on Render (~Starter each). To run two
> services instead of three, drop `focusstream-beat` and give the worker embedded
> beat: `celery -A app.core.celery_app.celery_app worker -B` (fine for a single
> worker).

## Tests

```bash
pip install -r requirements-dev.txt
pytest                      # unit tests run anywhere; integration tests skip if no DB
```

- **Unit tests** (`test_scoring`, `test_ingestion_parsing`, `test_display_status`,
  `test_transcription`) need no infra — the embedder, transcriber, and audio
  decoder are stubbed; feed parsing runs offline on XML strings.
- **Integration tests** (`test_api`, `test_pipeline`) need Postgres+pgvector and
  **skip cleanly** when it's absent. They stub the embedder (OpenAI) and
  synthesizer (Claude) but run the real pgvector cosine match. Point them at a
  throwaway DB:

```bash
POSTGRES_HOST=localhost POSTGRES_DB=focusstream_test pytest
# or against the compose DB:
docker compose exec api sh -c "POSTGRES_DB=focusstream_test pytest"
```

Celery `.delay` is stubbed globally (a `MagicMock`), so no broker is needed and
task dispatches are asserted directly.

## Migrations

```bash
docker compose exec api alembic upgrade head        # apply
docker compose exec api alembic revision -m "msg"   # new revision (edit by hand)
```

## Layout

```
app/
  api/        # FastAPI routers (request path only)
  core/       # config, db engines, celery app
  models/     # SQLAlchemy models (User, Sprint, RawFeedItem, SignalCard, Feedback)
  schemas/    # Pydantic request/response models
  services/   # embeddings (OpenAI), llm (Claude), scoring/tiers
  workers/    # Celery tasks: embed_sprint_intent, embed_content_item, match_item_to_sprints
alembic/      # migration environment + versions
```

## Design notes

- **Async embedding on create.** `POST /sprints` returns in ~ms with
  `embedding_status: "queued"`; the sprint becomes matchable once the worker
  writes its `intent_embedding`. The UI shows an "Indexing Intent…" state.
- **Tier thresholds live in config**, not the DB (`HIGH_SIGNAL_THRESHOLD`,
  `CONTEXTUAL_THRESHOLD`) — tune against real score distributions with no migration.
- **Synthesis is cost-gated.** Only tiers in `synthesize_tiers` (default
  `high_signal`) get an LLM call; low-signal matches are archived without one.
- **Embedding dimension is 1536, not 3072.** pgvector's HNSW/IVFFlat indexes cap
  at 2000 dims; `text-embedding-3-large` supports Matryoshka truncation via the
  `dimensions` param, keeping near-full quality while staying indexable.

## Ingestion

Content sources live in the `sources` table (RSS / newsletter / podcast feed
URLs). Celery beat runs `ingestion.poll_all_sources` every `POLL_INTERVAL_SECONDS`
(default 15 min), which fans out one `poll_source` per active source. Each poll:

1. fetches + parses the feed (`feedparser`),
2. inserts new items into `raw_feed_items`, deduped by `content_hash`,
3. dispatches `embed_content_item.delay(item_id)` — which embeds, then matches
   against active sprints and synthesizes takeaways for high-signal hits.

### See it light up

```bash
docker compose up --build
docker compose exec api python -m app.scripts.seed      # demo user usr_9921 + 4 RSS sources
docker compose exec worker python -m app.scripts.poll_now   # trigger a poll now (don't wait for beat)
```

Create a sprint (via the app or the curl above), wait a few seconds for embedding
+ matching, then pull-to-refresh the feed. Signal Cards appear for items that
clear the contextual threshold.

### Podcasts (Whisper transcription)

Podcast sources are matched on the **spoken transcript**, not just show notes.
When `poll_source` ingests a podcast item (audio enclosure captured in
`raw_feed_items.audio_url`), it routes through `content.transcribe_podcast`
instead of straight to embedding:

1. download the audio, cap to `PODCAST_MAX_DURATION_MINUTES`, downsample to
   16 kHz mono, split into 10-min chunks (podcasts exceed Whisper's 25 MB limit),
2. transcribe each chunk (`whisper-1`) and concatenate,
3. set `body` to the transcript, then dispatch `embed_content_item`.

Transcription **degrades gracefully**: on any failure the item still embeds on
show notes alone. If a chunk transcript is empty it's skipped.

**Cost controls** (Whisper is ~$0.006/min):
- `PODCAST_MAX_EPISODES_PER_POLL` (default 5) — only the newest N episodes per
  poll are transcribed; older backlog embeds on show notes only.
- `PODCAST_MAX_DURATION_MINUTES` (default 120) — per-episode transcription cap.
- `TRANSCRIPTION_ENABLED=false` — disable entirely.

Requires `ffmpeg` (in the Docker image) and `pydub`. The seeded "Talk Python To
Me" podcast source is **inactive by default** — enable it to test:

```bash
docker compose exec db psql -U focusstream -c \
  "UPDATE sources SET is_active = true WHERE type = 'podcasts';"
docker compose exec worker python -m app.scripts.poll_now
```
