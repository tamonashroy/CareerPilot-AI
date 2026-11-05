## 1. What we are building

CareerPilot AI helps a job seeker:

1. Build a verified professional profile from their CV.
2. Bring in relevant jobs from permitted sources.
3. See how well each job matches their profile, and why.
4. Generate a tailored CV and cover letter that only use facts they have confirmed.
5. Track each application from shortlist to outcome.

The first user is the product owner. The code is still built as a multi-user product from day one, so it can later become a paid SaaS without a rewrite. **We build the smallest version that works end to end, use it for real, and add features only when real use shows they are needed.**

## 2. Non-negotiable rules

These apply to every increment. They are the reason the product can be trusted.

**Truthfulness of candidate data**
- Never invent skills, employers, dates, metrics, certifications or years of experience.
- Every fact in the profile carries a `source` (cv, manual, voice) and a `status` (extracted, confirmed). Only `confirmed` facts may appear in generated CVs, cover letters or answers.
- Every claim in a generated document must trace back to one or more confirmed profile fact IDs. Store that mapping.

**Data isolation**
- Every user-owned table has an `owner_id`. All reads and writes go through a repository/service layer that scopes by the authenticated user. Never accept `user_id` from the client.
- A cross-user access test exists for every user-owned resource and must pass in CI.

**Job sources and applications**
- Use only official APIs, public job-board APIs, user-pasted URLs/text, or job-alert emails the user forwards.
- Never scrape behind a login, bypass CAPTCHAs, OTPs, rate limits or anti-bot measures, or automate LinkedIn, Naukri or similar portals.
- The MVP never submits applications. The user submits them through the employer's own link (manual handoff), and the app records the result.
- Never auto-answer legal declarations, work authorisation, salary confirmation or other sensitive questions.

**AI safety**
- Treat CVs, job descriptions and all third-party text as untrusted data. Put it in clearly delimited data blocks, never in the instruction section of a prompt.
- AI output never triggers an external action directly. It is validated against a Pydantic schema, then stored as a draft for the user.
- If AI output fails validation, retry once with the validation error, then fail cleanly. A failed AI call must never modify existing confirmed data.

**Secrets**
- No secrets in code, commits or frontend. Provide `.env.example` with a description for every variable.

## 3. Technology choices (MVP)

Keep the stack small. Add infrastructure only when a measured need appears, and record why in an ADR.

| Area | MVP choice | Add later when… |
|---|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic | — |
| Database | PostgreSQL 16 + pgvector (Docker locally, Neon later) | Row-level security when there are external paying users |
| Background jobs | A PostgreSQL-backed job queue (a `jobs` table polled with `SELECT … FOR UPDATE SKIP LOCKED`, or a library such as Procrastinate). One worker process. | Redis/Celery only if queue throughput or latency becomes a measured problem |
| Scheduling | One scheduler loop that enqueues due searches idempotently (unique key per search per time slot) | — |
| AI | One provider (Anthropic) behind an `LLMProvider` interface, plus a deterministic mock provider for tests. Prompts are versioned files. Log model, tokens, cost and latency per call. | Second provider when there is a cost or quality reason |
| File storage | `Storage` interface with a local-disk implementation | S3-compatible implementation at deployment |
| Documents | `pypdf`/`pdfplumber` and `python-docx` for parsing; `python-docx` for generated CVs | PDF export, design templates |
| Auth | Email + password (argon2), email verification, password reset, Google OIDC. Server-side sessions in HTTP-only, secure, SameSite cookies. Roles: `user`, `admin`. | Microsoft, GitHub and other providers; MFA |
| Email | `EmailSender` interface; console sender in development, one transactional provider in staging | WhatsApp or other channels |
| Frontend | React, TypeScript, Vite, Tailwind, shadcn/ui, React Router, TanStack Query, React Hook Form, Zod | — |
| Quality | Ruff (lint + format), mypy on the service layer, pytest, ESLint, Prettier, Vitest; Playwright for 2–3 critical flows | Load tests before public launch |
| Delivery | Docker Compose (db, api, worker, web), GitHub Actions CI | Staging and production deployment |

Architecture is a **modular monolith**: one backend codebase with modules `auth`, `profile`, `jobs`, `matching`, `documents`, `applications`, `notifications`, `admin`. Modules talk through service functions, not through each other's tables.

**Seam for future subscriptions:** from day one, guard premium-able actions with a single `require_feature("feature_key")` dependency backed by a small `features` / `user_features` table. In the MVP every user has every feature. This makes billing a later addition, not a refactor.

## 4. How you (Claude Code) should work

**Per increment**
1. Read `DEVELOPMENT_STATUS.md` and the increment's scope in `docs/ROADMAP.md`.
2. Enter plan mode and present a short plan: files and modules to touch, database changes, API endpoints, UI screens, tests, and risks. Wait for my approval. This is the one checkpoint per increment.
3. After approval, implement autonomously as a vertical slice: migration + model + service + API + UI + tests together.
4. Run linters and the full test suite. Fix failures. Do not report a test as passing unless you ran it.
5. Update `DEVELOPMENT_STATUS.md` with what was done, the actual test command output summary, known issues, and the next step.
6. Use small, logical commits with Conventional Commit messages (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
7. Stop at the end of the increment and give me a short summary plus manual test steps I can follow.

**Decisions**
- Make ordinary technical decisions yourself. For anything significant (a new dependency, a pattern that is hard to reverse), add a short ADR in `docs/adr/NNNN-title.md`: context, decision, alternatives, consequences.
- Ask me only for credentials, spending money, legal/business approval, or genuine personal preference.
- If an external service is unavailable, build the interface plus a mock, put the real integration behind a feature flag, and mark it "blocked by credentials".

**Honesty about status.** Label every feature in `DEVELOPMENT_STATUS.md` as one of: Implemented & tested · Implemented, untested · Mocked · Blocked (needs X) · Not started.

**Avoid**
- Building features outside the current increment.
- Placeholder TODOs in core logic, or fake data in place of real backend calls.
- Rewriting working code that is unrelated to the current increment.
- Writing documentation for features that do not exist yet.

**Documentation kept current (only these in the MVP):** `README.md` (what it is, quick start), `docs/ARCHITECTURE.md` (one page plus a diagram), `docs/ROADMAP.md`, `docs/adr/`, `DEVELOPMENT_STATUS.md`, `.env.example`. FastAPI's OpenAPI page serves as API documentation.

## 5. Engineering standards

- **API:** versioned under `/api/v1`, consistent error format (`{"error": {"code", "message", "details"}}`), cursor or offset pagination on lists, request correlation ID on every request and log line.
- **Database:** UUID primary keys, `created_at`/`updated_at` in UTC, foreign keys with explicit `ON DELETE` behaviour, unique constraints for every business rule that forbids duplicates. Large files go in storage, not in the database. Every migration has a working downgrade.
- **Background jobs:** every job is idempotent (has an idempotency key), has a timeout, a max-attempt count with exponential backoff, and ends in `succeeded`, `failed` or `dead`. Jobs left `running` past their timeout are reclaimed. Expensive work (parsing, AI calls, discovery, emails) never runs inside an HTTP request.
- **Files:** validate type by content, not extension; size limit (e.g. 10 MB); reject password-protected or corrupted files with a clear message.
- **Security:** rate limiting on auth endpoints, CSRF protection for cookie-authenticated writes, strict CORS, secure headers, structured JSON logs that never contain secrets or full CV text.
- **Frontend:** loading, empty and error states on every screen; accessible components; light and dark themes; no hard-coded or mock data outside tests and Storybook-style fixtures.

