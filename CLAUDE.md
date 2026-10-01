# CLAUDE.md — Canadian Halal & Muslim-Owned Business Directory

This file is the build spec and working rules for Claude Code. Read it fully before writing code. Work phase by phase (Section 9), finish each phase's acceptance criteria, then stop and summarize before moving on.

---

## 1. What we are building

A system that collects publicly listed, self-identified halal-certified and Muslim-owned businesses in Canada from trustworthy sources, cleans and de-duplicates them, stores them with full provenance, and serves them through a website with a live dashboard, searchable directory, map, and CSV export.

There are three deliverables:

1. **Scraper/ETL worker** (Python). It fetches sources politely, parses them, normalizes, geocodes, de-duplicates and merges. It writes to PostgreSQL and emits live events.
2. **Website** (Next.js). It has a dashboard with live updates, a directory, a map, business detail pages with provenance, a source health page, an admin area, and correction/removal/claim forms.
3. **CSV export.** It is generated on demand (filtered) from the site and as a daily snapshot file `exports/businesses.csv`.

---

## 2. Non-negotiable working rules for Claude Code

1. **Never invent data.**
   - Do not create placeholder, sample or "example" businesses in the production database, the CSV, seed scripts, or the UI.
   - If a source can't be scraped, the result is zero rows from that source, not made-up rows.
2. **Never infer religion or ownership.** A business is marked `muslim_owned = self_identified` only when the source is one where the business itself declared it. Examples: a community directory the owner submitted to, or the business's own site saying so. Never use names, ethnicity, language, photos, location or cuisine as signals.
3. **Halal-certified ≠ Muslim-owned.**
   - These are separate fields.
   - Certifier lists include large non-Muslim-owned companies; never copy `halal_status` into `muslim_owned`.
4. **Inspect before you parse.**
   - For every source, do these steps before writing an adapter:
     - Fetch the live page.
     - Read `robots.txt`.
     - Note the Terms of Service.
     - Save 2–3 real HTML pages to `scraper/tests/fixtures/<source_id>/`.
   - Only then write selectors against those fixtures.
   - If robots.txt disallows the paths or the ToS forbids scraping, do not build the adapter. Record it in `docs/sources.md` as "permission required" and tell the user.
5. **Business data only, not personal data.**
   - Store business name, category, business address, business phone, website, and role emails (info@, sales@, orders@, contact@).
   - Do not store personal names, personal emails, home addresses, personal social profiles or photos of people.
   - Owner details enter the system only through the opt-in "Claim your listing" form.
6. **Every field must be traceable.** Each stored value records which listing (source + URL + timestamp) it came from (`field_provenance` table).
7. **Ask the user before adding any new source** not listed in Section 4.
8. **Secrets live in `.env`**, never in code or commits. Keep `.env.example` up to date.
9. Each phase ends with passing tests (`pytest`, `pnpm test`, `pnpm lint`, `pnpm typecheck`) and a short summary of what changed.

---

## 3. Tech stack

| Layer | Choice | Notes |
|---|---|---|
| Database | PostgreSQL 16 + `pg_trgm` + `pgcrypto` | Plain SQL migrations via `dbmate` (language-agnostic, single source of truth) |
| Scraper | Python 3.12, `uv`, `httpx`, `selectolax`, `pydantic` v2, `phonenumbers`, `rapidfuzz`, `tenacity`, `psycopg` v3, `typer`, `APScheduler` | Playwright only as a fallback for JS-rendered pages |
| Web | Next.js (latest stable, App Router), TypeScript strict, Tailwind, shadcn/ui, Drizzle ORM (introspected from SQL), TanStack Table, Recharts, react-leaflet + marker clustering | |
| Real-time | Postgres `LISTEN/NOTIFY` → Server-Sent Events route in Next.js | Needs a direct (non-pooled) DB connection |
| Auth (admin only) | Auth.js with a single admin credential from env (bcrypt hash) | |
| Geocoding | Nominatim (1 req/sec, identifying UA, cached) | Optional paid geocoder behind an interface |
| Infra | Docker Compose: `db`, `worker`, `web` | A VPS is recommended because SSE needs long-lived connections |

---

## 4. Data sources

Source types and default trust rank (1 = most trusted for the fields it covers):

| source_id | Source | Type | Trust | What it gives | Status |
|---|---|---|---|---|---|
| `hma_*` | Halal Monitoring Authority (HMA) Canada — certified stores, restaurants, suppliers, processed meat, non-meat products, home-based businesses | certifier | 1 | Halal certification, certifier, some expiry dates, business address/phone/website | Verified to exist. Inspect before building |
| `hicc_bc` | Halal Inspection & Certification Committee (HICC), BC Muslim Association | certifier | 1 | BC certified facilities | **Find the official current URL first**; do not use third-party re-uploads (e.g. Scribd copies). These are stale and not the authoritative source |
| `hmca` | Halal Montreal Certification Authority | certifier | 1 | Quebec/other certified clients, if a public client list exists | **Find the official URL and check whether a public list exists** |
| `jaffari_dir` | Jaffari Business Directory (ISIJ of Toronto) — `https://jaffari.org/directory/` (also `?view=list`) | community_directory (self-submitted) | 2 | Self-identified community-owned businesses, GTA | Verified to exist. The page disclaims accuracy of listings, so confidence is moderate |
| `osm_overpass` | OpenStreetMap via Overpass API, `diet:halal=yes|only` | open_data (ODbL) | 3 | Halal-serving food places across Canada, coordinates | Legally clean with attribution. Start here |
| — | Ontario Muslim Chamber of Commerce member directory | community_directory | 2 | Self-identified Muslim-owned businesses | **Only if a public member directory exists and terms allow** |
| — | Commercial Muslim directory apps/sites (e.g. Muslim Directory App, halal restaurant review sites) | — | — | — | **Do not scrape.** Their ToS typically forbid it. List them in `docs/sources.md` as "partnership/API request" |

Known HMA URL patterns (inspect live, they may change):
- `https://hmacanada.org/`
- `https://hma.hmacanada.org/hma-certified-stores/`
- `https://hma.hmacanada.org/hma-processed-meat-deli-products/`
- Detail pages such as `https://hmacanada.org/non-meat-products/<slug>/` and `https://hma.hmacanada.org/<slug>`

HMA serves pages from several hostnames (`hmacanada.org`, `hma.hmacanada.org`, `new.hmacanada.org`). **Canonicalize to one host + path before using a URL as `source_record_key`**, or you will create duplicates.

HMA detail pages may list a certification expiry date. Parse it into `certification_expires`. Supplier pages may list a named contact person and personal email. Per Rule 5, **do not store the person's name or a non-role email**.

Product-level "Halal Check" rulings on HMA are about products, not businesses. They are out of scope.

Overpass query (Canada, halal-tagged places):

```
[out:json][timeout:300];
area["ISO3166-1"="CA"][admin_level=2]->.ca;
nwr["diet:halal"~"^(yes|only)$"](area.ca);
out center tags;
```

Map OSM tags as follows:
- Name: `name`, `name:en`, `name:fr`
- Category: `amenity`, `shop`, `cuisine`
- Address: `addr:housenumber`, `addr:street`, `addr:city`, `addr:province`, `addr:postcode`
- Contact: `phone` / `contact:phone`, `website` / `contact:website`
- Certification: `halal:certification` (if present)

Treat `disused:*` / `was:*` prefixes as closed. OSM data → `halal_status = community_tagged`, `muslim_owned = not_stated`. Display "© OpenStreetMap contributors (ODbL)" attribution on the site and in the CSV header comment/README.

Optional verification (later phase, behind a flag): Google Places API can confirm `business_status` (operational/closed). Check current Google Maps Platform terms before storing anything. Generally only `place_id` may be stored long-term, so store just `place_id`, the verified status, and a timestamp.

---

## 5. Repository layout

```
muslim-business-directory/
├── CLAUDE.md
├── README.md
├── docker-compose.yml
├── .env.example
├── docs/
│   ├── sources.md            # each source: URL, robots/ToS notes, status, last inspected
│   ├── methodology.md        # what each field means, confidence scoring, limits
│   └── data-dictionary.md    # CSV columns
├── db/
│   └── migrations/           # dbmate SQL files
├── exports/                  # daily CSV snapshots (gitignored)
├── data/raw/                 # raw HTML/JSON per source per run (gitignored)
├── scraper/
│   ├── pyproject.toml
│   ├── src/mbd/
│   │   ├── cli.py            # typer: scrape, export, worker, verify, stats
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── models.py         # pydantic: RawListing, NormalizedListing
│   │   ├── events.py         # pg_notify helpers
│   │   ├── fetch/
│   │   │   ├── http.py       # httpx client, retries, conditional GET
│   │   │   ├── robots.py
│   │   │   └── ratelimit.py  # per-domain token bucket
│   │   ├── sources/
│   │   │   ├── base.py       # SourceAdapter ABC
│   │   │   ├── osm_overpass.py
│   │   │   ├── hma.py
│   │   │   ├── jaffari_dir.py
│   │   │   └── ...           # only after inspection + user approval
│   │   ├── pipeline/
│   │   │   ├── normalize.py
│   │   │   ├── geocode.py
│   │   │   ├── dedupe.py
│   │   │   ├── merge.py
│   │   │   ├── validate.py
│   │   │   └── lifecycle.py  # missing-run tracking, expiry, closure
│   │   ├── export/csv.py
│   │   └── scheduler.py
│   └── tests/
│       ├── fixtures/<source_id>/*.html|json   # REAL captured pages
│       ├── test_parsers.py
│       ├── test_normalize.py
│       ├── test_dedupe.py
│       └── test_export.py
└── web/
    ├── package.json
    ├── drizzle.config.ts
    └── src/
        ├── app/
        │   ├── page.tsx                 # Dashboard
        │   ├── directory/page.tsx
        │   ├── map/page.tsx
        │   ├── business/[id]/page.tsx
        │   ├── sources/page.tsx
        │   ├── about/page.tsx           # methodology, attribution, accuracy stats
        │   ├── claim/[id]/page.tsx
        │   ├── report/[id]/page.tsx     # correction / removal
        │   ├── admin/...                # protected
        │   └── api/...
        ├── components/
        └── lib/ (db.ts, queries.ts, filters.ts, sse.ts)
```

---

## 6. Database schema (`db/migrations/001_init.sql`)

```sql
-- migrate:up
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TYPE halal_status AS ENUM
  ('certified','certification_lapsed','self_declared','community_tagged','unknown');
CREATE TYPE ownership_status AS ENUM ('self_identified','not_stated');
CREATE TYPE business_status  AS ENUM ('active','possibly_closed','closed');
CREATE TYPE source_type      AS ENUM ('certifier','community_directory','open_data');
CREATE TYPE run_status       AS ENUM ('queued','running','succeeded','partial','failed');

CREATE TABLE sources (
  id              text PRIMARY KEY,
  name            text NOT NULL,
  type            source_type NOT NULL,
  base_url        text NOT NULL,
  trust_rank      int  NOT NULL,
  interval_hours  int  NOT NULL DEFAULT 24,
  enabled         boolean NOT NULL DEFAULT true,
  terms_notes     text,
  attribution     text,
  robots_checked_at timestamptz
);

CREATE TABLE businesses (
  id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name                   text NOT NULL,
  name_normalized        text NOT NULL,
  category               text NOT NULL,   -- restaurant|grocery_butcher|supplier_manufacturer|bakery_cafe|services|retail|other
  subcategory            text,
  address_line           text,
  city                   text,
  province               char(2) CHECK (province IN
                           ('AB','BC','MB','NB','NL','NS','NT','NU','ON','PE','QC','SK','YT')),
  postal_code            text CHECK (postal_code ~ '^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$'),
  latitude               double precision,
  longitude              double precision,
  phone_e164             text,
  website                text,
  email                  text,            -- role addresses only
  halal_status           halal_status NOT NULL DEFAULT 'unknown',
  certifier              text,
  certification_expires  date,
  muslim_owned           ownership_status NOT NULL DEFAULT 'not_stated',
  ownership_evidence_url text,
  status                 business_status NOT NULL DEFAULT 'active',
  confidence             numeric(3,2) NOT NULL DEFAULT 0.50,
  claimed                boolean NOT NULL DEFAULT false,
  hidden                 boolean NOT NULL DEFAULT false,  -- removal requests
  first_seen_at          timestamptz NOT NULL DEFAULT now(),
  last_seen_at           timestamptz NOT NULL DEFAULT now(),
  last_verified_at       timestamptz,
  updated_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX businesses_name_trgm ON businesses USING gin (name_normalized gin_trgm_ops);
CREATE INDEX ON businesses (province, city);
CREATE INDEX ON businesses (category);
CREATE INDEX ON businesses (halal_status);
CREATE INDEX ON businesses (muslim_owned);

CREATE TABLE listings (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id         text NOT NULL REFERENCES sources(id),
  source_record_key text NOT NULL,   -- canonical URL, or "osm:node/123"
  source_url        text NOT NULL,
  business_id       uuid REFERENCES businesses(id) ON DELETE SET NULL,
  raw               jsonb NOT NULL,
  content_hash      text NOT NULL,
  first_seen_at     timestamptz NOT NULL DEFAULT now(),
  last_seen_at      timestamptz NOT NULL DEFAULT now(),
  missing_runs      int NOT NULL DEFAULT 0,
  UNIQUE (source_id, source_record_key)
);

CREATE TABLE field_provenance (
  business_id  uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  field        text NOT NULL,
  value        text,
  listing_id   uuid NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  observed_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (business_id, field, listing_id)
);

CREATE TABLE scrape_runs (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id        text NOT NULL REFERENCES sources(id),
  status           run_status NOT NULL DEFAULT 'queued',
  triggered_by     text NOT NULL DEFAULT 'schedule',   -- schedule|admin|cli
  started_at       timestamptz,
  finished_at      timestamptz,
  pages_fetched    int NOT NULL DEFAULT 0,
  records_new      int NOT NULL DEFAULT 0,
  records_updated  int NOT NULL DEFAULT 0,
  records_unchanged int NOT NULL DEFAULT 0,
  records_missing  int NOT NULL DEFAULT 0,
  errors           jsonb NOT NULL DEFAULT '[]'
);

CREATE TABLE geocode_cache (
  query      text PRIMARY KEY,
  latitude   double precision,
  longitude  double precision,
  provider   text NOT NULL,
  raw        jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE review_queue (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind       text NOT NULL,   -- possible_duplicate|low_confidence|parse_anomaly|claim|report
  payload    jsonb NOT NULL,
  status     text NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz
);

CREATE TABLE removal_requests (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id uuid REFERENCES businesses(id) ON DELETE CASCADE,
  contact     text NOT NULL,
  reason      text,
  status      text NOT NULL DEFAULT 'open',
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE listing_claims (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  business_id   uuid NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
  owner_name    text NOT NULL,       -- consented, shown only if public_owner=true
  owner_email   text NOT NULL,       -- never shown publicly
  public_owner  boolean NOT NULL DEFAULT false,
  self_identifies_muslim_owned boolean NOT NULL,
  consent_text  text NOT NULL,       -- exact consent wording shown
  verified      boolean NOT NULL DEFAULT false,  -- email + admin check
  created_at    timestamptz NOT NULL DEFAULT now()
);

-- migrate:down
DROP TABLE IF EXISTS listing_claims, removal_requests, review_queue, geocode_cache,
  scrape_runs, field_provenance, listings, businesses, sources CASCADE;
DROP TYPE IF EXISTS run_status, source_type, business_status, ownership_status, halal_status;
```

Seed `sources` rows only (in `002_sources.sql`) for sources that passed inspection. No business seed data, ever.

---

## 7. Scraper design

### 7.1 Polite fetching (`fetch/`)

- Use one `httpx.Client` with an identifying User-Agent from env, e.g. `CanadaHalalDirectoryBot/1.0 (+https://<domain>/about; <contact-email>)`.
- Check `robots.txt` with `urllib.robotparser`. Cache it for 24h. Skip disallowed URLs and log them.
- Use a per-domain rate limit: default 1 request every 3 seconds, configurable per source. Never run parallel requests against the same domain.
- Retry with `tenacity`: exponential backoff on 429/5xx/timeouts, max 4 attempts. Honor `Retry-After`.
- Make conditional requests with `ETag` / `If-Modified-Since`. A 304 counts as "unchanged".
- Save every raw response to `data/raw/<source_id>/<YYYY-MM-DD>/<sha1(url)>.html|json` for reproducibility and debugging.
- Use Playwright only if inspection shows the content is rendered client-side. Document it in `docs/sources.md`.

### 7.2 Adapter interface (`sources/base.py`)

```python
class SourceAdapter(ABC):
    source_id: str
    def discover(self, client) -> Iterable[str]: ...        # listing/detail URLs
    def parse(self, url: str, body: str) -> list[RawListing]: ...
```

`RawListing` (pydantic) has these fields: `source_record_key`, `source_url`, `name`, `category_hint`, `address_raw`, `city`, `province`, `postal_code`, `phone_raw`, `website`, `email`, `halal_status`, `certifier`, `certification_expires`, `muslim_owned`, `ownership_evidence_url`, `extra: dict`.

`parse` must be a pure function of `(url, body)` so it is fully testable with fixtures.

### 7.3 Normalization (`pipeline/normalize.py`)

- **Name.** Strip whitespace. Keep display casing. For `name_normalized`: casefold, remove punctuation, remove legal suffixes (inc, ltd, ltée, corp, co), and collapse spaces.
- **Phone.** Parse with `phonenumbers` (region `CA`) and store as E.164. Drop the phone if it is invalid.
- **Postal code.** Uppercase, format as `A1A 1A1`, and validate with the regex. Cross-check that the first letter matches the province (e.g. `M`/`K`/`L`/`N`/`P` = ON, `V` = BC, `H`/`J`/`G` = QC, `T` = AB, `R` = MB, `S` = SK, `E` = NB, `B` = NS, `C` = PE, `A` = NL, `X` = NT/NU, `Y` = YT). If they conflict, send the record to `review_queue`.
- **Province.** Map full names/French names/abbreviations to the 2-letter code.
- **Website.** Normalize the scheme and lowercase the host. Strip tracking params.
- **Email.** Keep it only if the local part is a role address. Otherwise discard it (Rule 5).
- **Category.** Use a deterministic mapping table from source categories and OSM tags into the fixed category set. Unknown values become `other`.

### 7.4 Geocoding (`pipeline/geocode.py`)

- Geocode only when the source gives no coordinates.
- Use Nominatim with a 1 req/sec limit, the required User-Agent and email, and `countrycodes=ca`. Cache every query in `geocode_cache`.
- Reject results outside Canada's bounding box, and results whose province disagrees with the record.

### 7.5 De-duplication and merge (`pipeline/dedupe.py`, `merge.py`)

Candidate match, in order:
1. Same `phone_e164`.
2. Same `website` host (excluding generic hosts like facebook.com, instagram.com, linktr.ee).
3. `rapidfuzz.token_set_ratio(name_normalized) >= 90` AND (same postal code OR distance ≤ 150 m).

If the score is ambiguous (80–90), do not auto-merge. Put the pair into `review_queue` as `possible_duplicate`.

Field precedence on merge: the lower `trust_rank` wins. Ties go to the most recently observed value. Every chosen value gets a `field_provenance` row.

`halal_status` precedence: `certified` > `certification_lapsed` > `self_declared` > `community_tagged` > `unknown`.

`muslim_owned = self_identified` comes only from sources/claims that are self-declarations. It is never derived from certifiers or OSM.

### 7.6 Lifecycle (`pipeline/lifecycle.py`)

- After each successful run of a source, increment `missing_runs` on its listings that were not seen.
- When a certifier listing reaches `missing_runs >= 2`:
  - If the business has no other certifier listing, set `halal_status = certification_lapsed`.
  - Never hard-delete.
- When `certification_expires < today`, set `halal_status = certification_lapsed`.
- If a website returns 404/410/DNS failure in 2 consecutive weekly checks, or OSM shows `disused:`/`was:`, set `status = possibly_closed`.
- Only an admin action or an explicit source signal sets `closed`.

### 7.7 Confidence score (0–1)

Start at the base for the best source type:

| Best source type | Base |
|---|---|
| certifier | 0.85 |
| community_directory | 0.70 |
| open_data | 0.60 |

Then adjust:
- +0.05 for each additional independent source agreeing on phone or address (max +0.10).
- −0.10 if `last_verified_at` is older than 180 days.
- −0.15 if `status = possibly_closed`.

Clamp the result to [0, 1]. Records below 0.5 go to `review_queue` (`low_confidence`), but they stay visible with a badge.

### 7.8 Events (`events.py`)

Emit `SELECT pg_notify('scrape_events', <json>)` at these points:
- Run started
- Every 25 records processed (progress)
- Each new business
- Run finished

Payload:
```json
{"type":"run_progress","run_id":"...","source_id":"hma_stores","pages":12,"new":3,"updated":5,"at":"2026-10-01T12:00:00Z"}
```

### 7.9 Scheduler and job queue (`scheduler.py`)

- The `mbd worker` command runs APScheduler. Each enabled source runs every `interval_hours`. Defaults: certifiers 24h, community directories 24h, OSM 24h, website health check weekly.
- The worker also `LISTEN`s on channel `scrape_jobs`. The admin "Run now" button inserts a `scrape_runs` row with `status='queued'` and notifies. The worker picks it up.
- Only one run per source at a time. Use a Postgres advisory lock per source_id.

### 7.10 CLI

```
uv run mbd scrape --source osm_overpass
uv run mbd scrape --all
uv run mbd export --out ../exports/businesses.csv [--province ON] [--halal-status certified]
uv run mbd verify --sample 25          # prints random records + source URLs for manual QA
uv run mbd stats
uv run mbd worker
```

---

## 8. CSV export spec

Encoding is UTF-8 with BOM (`utf-8-sig`) so Excel shows French accents correctly. Use RFC 4180 quoting, ISO 8601 dates, and one row per business. Hidden (removed) businesses are excluded.

| Column | Description |
|---|---|
| id | Stable UUID |
| business_name | Display name |
| category / subcategory | Fixed category set |
| address / city / province / postal_code | Business address |
| latitude / longitude | WGS84 |
| phone | E.164 |
| website / email | Email is role address only |
| halal_status | certified / certification_lapsed / self_declared / community_tagged / unknown |
| certifier | e.g. HMA |
| certification_expires | Date or empty |
| muslim_owned | self_identified / not_stated |
| ownership_evidence_url | Where the self-identification was found |
| status | active / possibly_closed / closed |
| confidence | 0.00–1.00 |
| sources | Pipe-separated source names |
| source_urls | Pipe-separated URLs |
| first_seen / last_verified | ISO 8601 |

Ship `docs/data-dictionary.md` alongside the CSV. Include OSM attribution in `README.md` and on the export page.

---

## 9. Build phases and acceptance criteria

### Phase 0 — Scaffold
- Create the monorepo, `docker-compose.yml` (postgres:16, worker, web), `.env.example`, Makefile/justfile, pre-commit (ruff, black, eslint, prettier).
- **Done when** `docker compose up db` works and `dbmate up` applies an empty migration.

### Phase 1 — Schema
- Implement Section 6. Seed only `sources` rows for OSM (and others after Phase 3 inspection).
- **Done when** migrations go up and down cleanly and Drizzle introspection generates types in `web/`.

### Phase 2 — Fetch core
- Implement Section 7.1 with unit tests: robots disallow respected, rate limiter timing, retry on 429, conditional GET.
- **Done when** tests pass with no live network (use `respx` mocks).

### Phase 3 — Source inspection (no parsers yet)
- For each source in Section 4:
  - Fetch the pages and read robots.txt and the ToS.
  - Save real fixtures.
  - Write a `docs/sources.md` entry: URL(s), allowed/disallowed, page structure, pagination, fields available, and any personal data present (and how it's excluded).
- **Stop and report to the user** before Phase 4.

### Phase 4 — Adapters
- Order: `osm_overpass` → `hma_*` → `jaffari_dir` → others approved in Phase 3.
- Each adapter has parser tests against its real fixtures, asserting exact field values from those pages.
- **Done when** `mbd scrape --source <id>` writes listings and `scrape_runs` rows, and a second run shows mostly `unchanged`.

### Phase 5 — Pipeline
- Implement normalize, geocode, dedupe, merge, provenance, lifecycle and confidence (Sections 7.3–7.7), each with unit tests.
- Dedupe tests must cover: same phone/different names, same name/different cities, multi-host HMA URLs.
- **Done when** `mbd stats` shows business counts by source and `mbd verify --sample 25` prints records that match their source pages.

### Phase 6 — Export, events, worker
- Implement the CSV export (Section 8), `pg_notify` events, the scheduler, and the job listener.
- **Done when** `exports/businesses.csv` opens correctly in Excel and LibreOffice, and the queued admin job is picked up within 5 seconds.

### Phase 7 — Website: read-only pages
- Dashboard, directory, map, business detail, sources, about (Section 10).
- **Done when** all pages render with real DB data, Lighthouse accessibility ≥ 90, and the mobile layout works.

### Phase 8 — Real-time
- SSE endpoint and live dashboard updates (Section 10.3).
- **Done when** running a scrape from the CLI updates dashboard counters and the activity feed without a page reload.

### Phase 9 — Admin and community forms
- Admin auth, run-now, review queue (merge/split duplicates, resolve anomalies), removal requests (hide within 1 action), claim-your-listing flow (email verification + admin approval), report-a-correction form.
- **Done when** every form is rate-limited, has CAPTCHA (Cloudflare Turnstile or hCaptcha), and is covered by tests.

### Phase 10 — Hardening and deploy
- Structured logging, a health endpoint, nightly DB backup, a daily CSV snapshot, a README deploy guide (VPS + Docker Compose + Caddy for HTTPS).
- Production map tiles must use a tile provider that allows production use. Do not hammer `tile.openstreetmap.org`.

---

## 10. Website spec

### 10.1 Pages

**Dashboard `/`**
- KPI cards. Define each metric exactly in `lib/queries.ts` and document it on `/about`:
  - Total listed businesses: `hidden = false AND status != 'closed'`.
  - Currently certified: `halal_status = 'certified' AND (certification_expires IS NULL OR certification_expires >= current_date)`.
  - Self-identified Muslim-owned: `muslim_owned = 'self_identified'`.
  - Provinces covered.
  - Added in the last 7 days.
  - Last successful scrape time.
- Charts:
  - Businesses by province (bar).
  - By category (bar).
  - Halal status breakdown.
  - Cumulative businesses over time by `first_seen_at` (line).
  - Certifications expiring in the next 60 days (table).
- Live activity feed of scrape runs (SSE).
- Data-freshness badge per source (green < 26h, amber < 72h, red otherwise).
- Mini map preview.

**Directory `/directory`**
- Server-side paginated table (TanStack Table).
- Text search uses trigram on the name.
- Filters: province, city, category, halal_status, certifier, muslim_owned, status, min confidence. Filters are reflected in the URL query string.
- "Download CSV" exports exactly the current filter.

**Map `/map`**
- Clustered markers. The bbox-based API loads only visible points.
- Same filters as the directory. Clicking a marker opens a summary card.

**Business `/business/[id]`**
- All fields, badges (certified/lapsed/community-tagged/self-identified), last verified date and confidence.
- Provenance panel: each field → source name, link, observed date.
- Buttons: "Report a correction", "Request removal", "Claim this listing".

**Sources `/sources`**
- Each source: type, last run status, duration, counts (new/updated/unchanged/missing), recent errors, next scheduled run.

**About `/about`**
- Methodology: what "certified", "community_tagged" and "self_identified" mean.
- The difference between halal-certified and Muslim-owned.
- That religion is never inferred.
- Source list with attribution (ODbL).
- Removal/correction policy.
- Latest manual QA accuracy rate (from monthly `mbd verify` reviews, entered by the admin).

**Admin `/admin/*`** (protected): run now per source, review queue, removal requests, claims, and a manual QA log entry form.

### 10.2 API routes (`app/api/`)

| Route | Purpose |
|---|---|
| `GET /api/stats` | KPIs + chart series |
| `GET /api/businesses` | Filters, search, sort, `page`, `pageSize` (max 100) |
| `GET /api/businesses/[id]` | Detail + provenance |
| `GET /api/geo?bbox=minLng,minLat,maxLng,maxLat&...filters` | Lightweight points for map |
| `GET /api/export.csv?...filters` | Streamed CSV, same columns as Section 8 |
| `GET /api/sources` | Source health |
| `GET /api/events` | SSE stream |
| `POST /api/admin/runs` | Queue a scrape (auth) |
| `POST /api/reports`, `/api/removal-requests`, `/api/claims` | Public forms (CAPTCHA + rate limit) |

Validate all inputs with `zod`. Never expose `hidden` businesses, owner emails or claim data through public routes.

### 10.3 Real-time

- `GET /api/events` is a Node-runtime route handler.
- It opens one shared `pg` client on `DATABASE_URL_DIRECT` that `LISTEN`s on `scrape_events`, and fans messages out to connected SSE clients.
- Send a heartbeat comment every 25s.
- The client uses `EventSource`. On `run_progress` it updates the activity feed. On `run_finished` it invalidates the TanStack Query/SWR caches for stats and sources.
- If SSE disconnects, auto-reconnect and fall back to polling `/api/stats` every 60s.

### 10.4 UI quality

- Clean, accessible design using shadcn/ui components. Support dark mode.
- Show empty states that say honestly "No data yet from this source". Never use placeholder rows.
- The interface can be English first, but it must store and display French names and accents correctly.

---

## 11. Testing and data-quality checklist

- Parser tests use real fixtures and assert exact values.
- A property-style test for normalization: every exported postal code matches the regex, and every phone parses as valid CA.
- Integration test: run the pipeline on fixtures into a temp DB, then export CSV and diff against an expected CSV built from the same fixtures.
- Monthly manual QA:
  - Run `mbd verify --sample 25` and open each source URL.
  - Record matches and mismatches in admin.
  - Publish the accuracy rate on `/about`.
- Alert (log + admin banner) when any of these happens:
  - A source returns 0 records when it previously returned > 0. This is likely a layout change, so do not mark everything missing. Set the run to `partial` and skip lifecycle updates.
  - Parse anomalies exceed 10% of records.

---

## 12. Privacy, legal and ethics guardrails

- Canada's privacy regulator treats religious information as sensitive. This project publishes business attributes that businesses have made public themselves, plus consented owner info via claims. It never publishes inferred religious information about individuals.
- Respect robots.txt and each site's Terms. If a terms page is unclear, ask permission from the site owner before scraping. Keep the inspection notes in `docs/sources.md`.
- Removal requests: hide the listing immediately on admin approval and exclude it from all exports. Keep only the minimal record needed to prevent re-adding it (`hidden = true`). Future scrapes must not un-hide it.
- Corrections: changes from reports go through the review queue, and the provenance shows "corrected by business/admin" with a date.
- Show attribution for OSM (ODbL) and name every source on detail pages.
- This spec is not legal advice. The operator should review the applicable terms and privacy obligations before going public.

---

## 13. Environment variables (`.env.example`)

```
DATABASE_URL=postgres://mbd:mbd@localhost:5432/mbd
DATABASE_URL_DIRECT=postgres://mbd:mbd@localhost:5432/mbd   # non-pooled, for LISTEN
SCRAPER_USER_AGENT="CanadaHalalDirectoryBot/1.0 (+https://example.org/about; contact@example.org)"
SCRAPER_DEFAULT_DELAY_SECONDS=3
NOMINATIM_EMAIL=contact@example.org
GOOGLE_PLACES_API_KEY=            # optional, verification only
AUTH_SECRET=
ADMIN_EMAIL=
ADMIN_PASSWORD_HASH=              # bcrypt
TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=
MAP_TILE_URL=                     # production tile provider URL template
MAP_TILE_ATTRIBUTION=
```

---

## 14. Definition of done (whole project)

- `docker compose up` brings up db, worker and web.
- The worker scrapes all approved sources on schedule. The dashboard updates live during runs.
- `exports/businesses.csv` is regenerated daily. Every row has at least one source URL, and the fields match the source pages in manual QA.
- No business in the database or CSV lacks a listing, and no field lacks provenance.
- No personal data beyond consented claim data. No inferred religion anywhere.
- README covers setup, running each command, adding a new source (inspection → approval → fixtures → adapter → tests), deployment and backups.
