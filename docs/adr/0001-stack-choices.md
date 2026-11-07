# ADR 0001: Stack choices for the foundation

**Status:** Accepted, 2026-11-05

## Context

`CLAUDE.md` sets the main stack: FastAPI, PostgreSQL 16 with pgvector, a PostgreSQL-backed job queue, React with Vite, and Docker Compose. It leaves some choices open. Increment 0 had to settle those, and it needed two small departures from the written plan. The project is developed on Windows and runs in Linux containers.

## Decisions

1. **Python tooling: `uv` with a committed lockfile.** One tool manages the Python version, dependencies and locking.
2. **Database access: async SQLAlchemy 2 with asyncpg.** Most future work waits on the network (AI calls, job sources), and `asyncio` timeouts can cancel that kind of work.
3. **Job queue: a small custom implementation, not Procrastinate.** `CLAUDE.md` allows either. Our rules on states, leases and fencing are specific, and about 200 lines that we can test directly are easier to reason about than adapting a library.
4. **Queue table name: `background_jobs`, not `jobs`.** This departs from the wording in `CLAUDE.md`, because Increment 3 needs `jobs` for job postings.
5. **Job outcomes.** `failed` means a permanent error where retrying can't help. `dead` means every allowed attempt was used. Both are final.
6. **Migrations: a one-shot `migrate` Compose service.** This adds a fifth service to the four in `CLAUDE.md`. It stops the API and worker from racing to migrate at startup.
7. **Probes: `/health` and `/ready` sit outside `/api/v1`.** They're for operators and aren't part of the versioned API. `/ready` also checks that the database is at the latest migration.
8. **pgvector: available but not enabled.** The image includes it, but `CREATE EXTENSION` waits until a feature uses it.
9. **Sample job trigger: CLI only.** There's no authentication yet, so an HTTP endpoint would let anyone add jobs.
10. **Frontend package manager: npm.** It comes with Node, and nothing here needs more.
11. **Later dependencies.** React Hook Form arrives with the first form and Playwright with the first critical flow. Only the shadcn/ui components in use are included.
12. **Containers don't mount source code.** This keeps Compose independent of the host's file system, including OneDrive, at the cost of needing a rebuild after changes. Native development gives hot reload.

## Alternatives considered

| Option | Why not |
|---|---|
| Procrastinate | A good library, but it adds concepts and its own schema for rules we can enforce in a small module. Worth revisiting if we need its features, such as periodic tasks or LISTEN/NOTIFY wakeups. |
| Redis with Celery | Ruled out by `CLAUDE.md` until there's a measured need. |
| psycopg 3 in async mode | It doesn't work with the default Windows event loop, which would make native development harder. |
| Sync SQLAlchemy | Simpler, but job timeouts would need threads, which can't be cancelled. |
| SQLite for tests | It has no `SKIP LOCKED`, so it can't test the queue's concurrency. |

## Consequences

- We own the queue code and its tests. Any change to it must keep the state rules in `docs/ARCHITECTURE.md`.
- **Timeouts only interrupt code that awaits.** CPU-heavy or blocking work, such as PDF parsing in Increment 2, must run in a separate process with its own limits. Otherwise a stuck job blocks the worker until the process is restarted.
- Jobs run at least once, so every handler must be idempotent.
- `background_jobs` has no `owner_id` because it's a system table. Jobs for a specific user must carry the owner explicitly, and handlers must scope their work by it.
- Polling every second keeps a database connection active. On a serverless database such as Neon, that can stop it scaling to zero, so this needs another look before deployment.
- Database tests need a real PostgreSQL server. CI requires them, using `REQUIRE_DB_TESTS=1`, so they can't be silently skipped.
