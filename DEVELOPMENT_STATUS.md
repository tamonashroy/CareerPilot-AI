# Development status

**Current increment:** 0 (Foundation), built on branch `feat/increment-0` and waiting for review and merge.
**Last updated:** 2026-11-05

## Roadmap "done when" for Increment 0

| Criterion | Result |
|---|---|
| `docker compose up` starts everything | Passed in CI on Linux. **Not yet run on the development PC**, because Docker isn't working there (see Known issues). |
| `/health` returns OK | Passed in CI through Compose, and locally as a native process. |
| The sample job runs | Passed in CI through Compose, and locally as a native process. |
| CI is green | Passed: all three jobs in [run 41960022424](https://github.com/tamonashroy/CareerPilot-AI/actions/runs/41960022424). |

## Features

| Feature | Status |
|---|---|
| Settings from the environment | Implemented & tested |
| JSON logs with redaction and correlation IDs | Implemented & tested |
| Error format, including clean 500s | Implemented & tested |
| Secure headers and CORS allowlist | Implemented & tested |
| `/health` and `/ready` | Implemented & tested |
| Alembic migrations, including downgrade | Implemented & tested |
| PostgreSQL 16 + pgvector in Compose | Implemented & tested (CI) |
| Job queue: idempotency, claiming, backoff, timeout, reclaim, fencing, final states | Implemented & tested |
| Worker loop and sample job | Implemented & tested |
| Worker stopping cleanly when asked | Implemented & tested (the stop logic only) |
| Worker's SIGTERM signal handler | Implemented, untested (nothing checks the signal triggers a stop) |
| Sample job CLI | Implemented & tested (CI smoke test and a local run) |
| React shell, routing and 404 page | Implemented & tested |
| System status page | Implemented & tested (component tests with a stubbed `fetch`) |
| Theme toggle | Implemented & tested (behaviour only) |
| Appearance in a real browser, light and dark | Implemented, untested (needs a manual look) |
| API client | Implemented & tested |
| CI workflow | Implemented & tested |
| Rate limiting and CSRF | Not started (Increment 1, with auth) |
| Increments 1–7 | Not started |

No features are mocked, and none are blocked by credentials yet.

## Latest check results

Run locally on Windows on 2026-11-05. Node was the portable 26.13.0 build. Database tests used an embedded PostgreSQL 16.2 with pgvector 0.6.2, not the Compose image.

| Command | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 31 files already formatted |
| `uv run mypy app` | No issues in 20 source files |
| `uv run pytest` (with `REQUIRE_DB_TESTS=1`) | 48 passed |
| `npm run lint` | No problems |
| `npm run format:check` | All files match |
| `npm run typecheck` | No errors |
| `npm test` | 16 passed (3 files) |
| `npm run build` | Built successfully |

There was also a local native run of the API, worker and Vite dev server together:
- `/ready` returned 503 before migrations and 200 after.
- The sample job reached `succeeded` on attempt 1.
- `/health` and `/ready` worked through the Vite proxy.

## Known issues

- **Docker doesn't work on the development PC.** WSL isn't installed and Docker Desktop is 4.5.1, from 2022.
- **The Node installer hasn't finished.** It was waiting for an administrator prompt at last check, so a system-wide Node may not be installed yet.
- **The repo is inside OneDrive.** `frontend/node_modules` is in the synced folder, and a future `.env` with real secrets would be uploaded too. Move the repo before Increment 1.
- **The worker's timeout only interrupts code that awaits.** Increment 2 must run PDF parsing in a separate process (see ADR 0001).
- **Roadmap gap:** Increment 7's unattended morning digest needs an always-on host, but deployment is in the post-MVP backlog. Decide this before Increment 7.

## Next step

Review and merge `feat/increment-0`, then plan Increment 1 (accounts and isolation). Increment 1 needs a Google OAuth client ID and secret.
