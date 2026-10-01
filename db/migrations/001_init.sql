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
