# CareerPilot AI

CareerPilot AI will help a job seeker build a verified profile from their CV, find relevant jobs from permitted sources, see how well each one matches, generate tailored documents using only confirmed facts, and track each application.

**Current state:** only the foundation exists (Increment 0): the API, worker, job queue and an app shell with a system status page. None of the product features above are built yet. See [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) and [docs/ROADMAP.md](docs/ROADMAP.md).

## Quick start

You need Docker Desktop with the WSL2 backend (or Docker Engine with Compose v2).

```sh
docker compose up --build
```

No `.env` file is needed for local use. To override a setting, copy `.env.example` to `.env`.

| What | Where |
|---|---|
| Web app | http://localhost:5173 |
| API docs | http://localhost:8000/docs |
| Liveness / readiness | http://localhost:8000/health, http://localhost:8000/ready |

Try the job queue from a second terminal:

```sh
docker compose exec api python -m app.cli enqueue-sample --message "hello"
docker compose exec api python -m app.cli job-status <job_id>
```

The job should show `"status": "succeeded"` and `"result": {"echo": "hello"}`.

To stop everything, run `docker compose down`. Adding `-v` also deletes the local database.

The containers don't mount your source code, so run `docker compose up --build` again after a change, or use the native setup below for hot reload.

## Developing without containers

You need [uv](https://docs.astral.sh/uv/) and Node 26. PostgreSQL can still run in Compose with `docker compose up -d db`.

If the repo is inside a synced folder such as OneDrive, set `UV_PROJECT_ENVIRONMENT` to a path outside it first, so the virtual environment doesn't sync.

**Backend** (from `backend/`, with `DATABASE_URL` set as in `.env.example`):

```sh
uv sync
uv run alembic upgrade head
uv run uvicorn app.asgi:app --reload
uv run python -m app.queue.worker
```

**Frontend** (from `frontend/`):

```sh
npm ci
npm run dev
```

## Checks

These are the same checks CI runs.

**Backend** (from `backend/`):

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

Database tests need PostgreSQL with pgvector and use `TEST_DATABASE_URL`. They skip if it's unreachable, unless `REQUIRE_DB_TESTS=1` is set, which makes them fail instead.

**Frontend** (from `frontend/`):

```sh
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Decision records](docs/adr/)
- [Development status](DEVELOPMENT_STATUS.md)
