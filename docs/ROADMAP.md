## MVP: increments 0–7

The MVP is done when I can use it daily: upload my CV, confirm my profile, get matched jobs every morning, generate a tailored CV for a job, apply via the employer's link, and track the outcome.

### Increment 0 — Foundation
- Repo layout: `backend/`, `frontend/`, `docker-compose.yml`, `.github/workflows/ci.yml`.
- FastAPI app with settings from environment, structured logging, correlation IDs, `/health` and `/ready` endpoints.
- Alembic set up with an initial empty migration. Postgres with pgvector in Compose.
- Worker process skeleton with the Postgres job queue and one sample job.
- React app shell with routing, theme toggle, API client.
- CI runs lint, type check and tests for backend and frontend.
- **Done when:** `docker compose up` starts everything, `/health` returns OK, the sample job runs, CI is green.

### Increment 1 — Accounts and isolation
- Register, verify email, log in, log out, reset password, Google sign-in.
- Session cookies, roles (`user`, `admin`), a seed command that makes my account admin.
- `require_feature()` seam and `features` tables (all enabled).
- Account deletion and data export endpoints (export can be a JSON bundle).
- **Tests:** auth flows; rate limiting; user A cannot read or change user B's data.
- **Done when:** I can create an account and sign in with email or Google, and the isolation test passes.

### Increment 2 — Profile from CV
- Upload PDF or DOCX → stored as the untouched original → background job extracts text → AI extracts a structured draft (experience, skills, projects, education, certifications, summary).
- Review screen: each extracted fact shown with its source text; user can edit, confirm or discard. Nothing becomes `confirmed` without user action.
- Manual add/edit for every profile section. Skills store name, proficiency, last used, and links to supporting experience.
- Profile is versioned: every confirmed change creates a new profile version.
- **Tests:** corrupted, oversized and password-protected files; invalid AI JSON; a failed extraction leaves the existing profile unchanged.
- **Done when:** I can upload my CV and end with a confirmed profile I trust.

### Increment 3 — Jobs in
- Common job model: canonical `jobs` plus per-source `job_listings` (title, company, description, required/preferred skills, experience, salary, location, remote eligibility incl. country restrictions, employment type, posted date, source, URL, requisition ID, content hash, last verified).
- Connector framework where each connector declares capabilities (`discover`, `fetch_detail`, `submit`); unsupported ones are disabled, never simulated.
- First connectors: (a) user pastes a job URL or raw description; (b) public Greenhouse and Lever job-board APIs for companies I list.
- AI normalises the description into the common model.
- Duplicate detection v1: normalised URL, requisition ID + company, and description hash. Uncertain matches are flagged, not merged.
- **Done when:** I can add jobs by pasting and by following target companies, with no duplicate entries.

### Increment 4 — Matching
- Search preferences (one or more saved profiles): titles, skills, salary range and currency, locations, remote/hybrid/onsite, countries I am eligible to work from, experience range, excluded companies and keywords, posting age.
- Stage 1: rule-based filters with a recorded reason for every rejection.
- Stage 2: AI match returning a validated object — overall score, sub-scores (technical, experience, seniority, domain), location and salary fit, strengths, gaps, concerns, recommendation, reasoning, and the profile facts used as evidence.
- Configurable weights per search profile. Re-score when the profile version changes.
- Shortlist UI with score breakdown, skill comparison, original link, save/dismiss, and thumbs up/down feedback.
- **Tests:** a US-only remote job is filtered out for an India-based user; a missing technology in the job text does not auto-reject.
- **Done when:** the shortlist ranks jobs the way I would, with explanations I agree with most of the time.

### Increment 5 — Tailored documents
- Generate a tailored CV (summary, skill emphasis, experience bullets) and an optional cover letter for a chosen job, using only confirmed facts.
- Fact check step: every generated statement maps to fact IDs; unmapped statements are highlighted and blocked from export until edited or removed.
- Edit in the UI, regenerate one section, compare with the master CV, export DOCX.
- Every document version stores job ID, profile version, prompt version, creation time and content hash. The master CV is never overwritten.
- **Done when:** I would actually send the generated CV without fixing invented content.

### Increment 6 — Application tracker with manual handoff
- One application per user per canonical job, enforced by a unique constraint.
- States: `SHORTLISTED → PREPARING → READY_FOR_REVIEW → APPROVED → SUBMITTED_BY_USER`, plus `WITHDRAWN` and `EXPIRED`; employer outcomes `ASSESSMENT`, `INTERVIEW`, `REJECTED`, `OFFER`, `HIRED`.
- Approval stores a snapshot hash of the documents and answers; any later edit invalidates the approval.
- Manual handoff screen: opens the employer's apply link, shows copy-ready documents and answers, then "I submitted this" records the time.
- Screening-answer drafts only for factual questions; sensitive questions are flagged for me to answer.
- Every state change is written to an append-only audit table and enforced by a single state-machine service.
- **Tests:** illegal transitions rejected; approval invalidated after a document edit; second application to the same job rejected.
- **Done when:** I track all my real applications here instead of a spreadsheet.

### Increment 7 — Daily discovery and digest
- Per search profile: enabled, frequency (daily or a few times a day, within a limit), preferred local time, timezone (stored UTC, DST-safe).
- Scheduler enqueues due searches in batches with an idempotency key per slot, so a double-running scheduler cannot create duplicate work.
- Daily email digest: new high-scoring jobs, applications awaiting my action, recent outcomes.
- Basic admin page: users, job queue (failed/dead jobs with retry), connector health, AI cost per day.
- **Tests:** worker crash mid-job → job is reclaimed and completed once; scheduler run twice → no duplicates.
- **Done when:** I receive a useful digest every morning without touching anything.

**After increment 7: use it for 2–4 weeks before building more.** Record pain points in `DEVELOPMENT_STATUS.md`; they decide the next increment.

## Post-MVP backlog (build only when the trigger is real)

| Feature | Build when… |
|---|---|
| Plans, entitlements, usage limits | Someone other than me will use it |
| Billing (Razorpay; Stripe for international) with verified, idempotent webhooks, grace periods, read-only on expiry | First paying customer is lined up |
| Public landing page, pricing, privacy policy and terms templates | Opening sign-ups |
| Full admin: plans, overrides with audit, feature flags, announcements | Multiple users |
| PostgreSQL row-level security | Multiple external tenants |
| Semantic duplicate detection (pgvector) and admin merge/unmerge | Duplicates slip through v1 rules |
| More connectors (official APIs, job-alert email ingestion) | A source is legally usable and I need it |
| Automated submission | A source officially permits it through an API, and manual handoff is a real bottleneck |
| Voice profile capture | Profile building from CV + manual is the main friction |
| PDF export and CV design templates | DOCX is not enough |
| Microsoft/GitHub sign-in, MFA | Users ask for it / before public launch |
| AI evaluation datasets and prompt A/B comparison | Before changing models or prompts in a way that affects matching or CV quality |
| Interview prep, skill-gap analysis, salary benchmarks, recruiter intelligence | Core loop is stable and users want more |
| Redis/Celery, load tests, staging + production deployment | Measured need / before public launch |

