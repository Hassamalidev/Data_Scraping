\restrict dbmate

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: business_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.business_status AS ENUM (
    'active',
    'possibly_closed',
    'closed'
);


--
-- Name: halal_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.halal_status AS ENUM (
    'certified',
    'certification_lapsed',
    'self_declared',
    'community_tagged',
    'unknown'
);


--
-- Name: ownership_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.ownership_status AS ENUM (
    'self_identified',
    'not_stated'
);


--
-- Name: run_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.run_status AS ENUM (
    'queued',
    'running',
    'succeeded',
    'partial',
    'failed'
);


--
-- Name: source_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.source_type AS ENUM (
    'certifier',
    'community_directory',
    'open_data'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: businesses; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.businesses (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    name_normalized text NOT NULL,
    category text NOT NULL,
    subcategory text,
    address_line text,
    city text,
    province character(2),
    postal_code text,
    latitude double precision,
    longitude double precision,
    phone_e164 text,
    website text,
    email text,
    halal_status public.halal_status DEFAULT 'unknown'::public.halal_status NOT NULL,
    certifier text,
    certification_expires date,
    muslim_owned public.ownership_status DEFAULT 'not_stated'::public.ownership_status NOT NULL,
    ownership_evidence_url text,
    status public.business_status DEFAULT 'active'::public.business_status NOT NULL,
    confidence numeric(3,2) DEFAULT 0.50 NOT NULL,
    claimed boolean DEFAULT false NOT NULL,
    hidden boolean DEFAULT false NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_verified_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT businesses_postal_code_check CHECK ((postal_code ~ '^[A-Z][0-9][A-Z] [0-9][A-Z][0-9]$'::text)),
    CONSTRAINT businesses_province_check CHECK ((province = ANY (ARRAY['AB'::bpchar, 'BC'::bpchar, 'MB'::bpchar, 'NB'::bpchar, 'NL'::bpchar, 'NS'::bpchar, 'NT'::bpchar, 'NU'::bpchar, 'ON'::bpchar, 'PE'::bpchar, 'QC'::bpchar, 'SK'::bpchar, 'YT'::bpchar])))
);


--
-- Name: field_provenance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.field_provenance (
    business_id uuid NOT NULL,
    field text NOT NULL,
    value text,
    listing_id uuid NOT NULL,
    observed_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: geocode_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.geocode_cache (
    query text NOT NULL,
    latitude double precision,
    longitude double precision,
    provider text NOT NULL,
    raw jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: listing_claims; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listing_claims (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    business_id uuid NOT NULL,
    owner_name text NOT NULL,
    owner_email text NOT NULL,
    public_owner boolean DEFAULT false NOT NULL,
    self_identifies_muslim_owned boolean NOT NULL,
    consent_text text NOT NULL,
    verified boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: listings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.listings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id text NOT NULL,
    source_record_key text NOT NULL,
    source_url text NOT NULL,
    business_id uuid,
    raw jsonb NOT NULL,
    content_hash text NOT NULL,
    first_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    last_seen_at timestamp with time zone DEFAULT now() NOT NULL,
    missing_runs integer DEFAULT 0 NOT NULL
);


--
-- Name: removal_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.removal_requests (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    business_id uuid,
    contact text NOT NULL,
    reason text,
    status text DEFAULT 'open'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: review_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.review_queue (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    kind text NOT NULL,
    payload jsonb NOT NULL,
    status text DEFAULT 'open'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone
);


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    version character varying NOT NULL
);


--
-- Name: scrape_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scrape_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    source_id text NOT NULL,
    status public.run_status DEFAULT 'queued'::public.run_status NOT NULL,
    triggered_by text DEFAULT 'schedule'::text NOT NULL,
    started_at timestamp with time zone,
    finished_at timestamp with time zone,
    pages_fetched integer DEFAULT 0 NOT NULL,
    records_new integer DEFAULT 0 NOT NULL,
    records_updated integer DEFAULT 0 NOT NULL,
    records_unchanged integer DEFAULT 0 NOT NULL,
    records_missing integer DEFAULT 0 NOT NULL,
    errors jsonb DEFAULT '[]'::jsonb NOT NULL
);


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id text NOT NULL,
    name text NOT NULL,
    type public.source_type NOT NULL,
    base_url text NOT NULL,
    trust_rank integer NOT NULL,
    interval_hours integer DEFAULT 24 NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    terms_notes text,
    attribution text,
    robots_checked_at timestamp with time zone
);


--
-- Name: businesses businesses_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.businesses
    ADD CONSTRAINT businesses_pkey PRIMARY KEY (id);


--
-- Name: field_provenance field_provenance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.field_provenance
    ADD CONSTRAINT field_provenance_pkey PRIMARY KEY (business_id, field, listing_id);


--
-- Name: geocode_cache geocode_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.geocode_cache
    ADD CONSTRAINT geocode_cache_pkey PRIMARY KEY (query);


--
-- Name: listing_claims listing_claims_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_claims
    ADD CONSTRAINT listing_claims_pkey PRIMARY KEY (id);


--
-- Name: listings listings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_pkey PRIMARY KEY (id);


--
-- Name: listings listings_source_id_source_record_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_source_id_source_record_key_key UNIQUE (source_id, source_record_key);


--
-- Name: removal_requests removal_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.removal_requests
    ADD CONSTRAINT removal_requests_pkey PRIMARY KEY (id);


--
-- Name: review_queue review_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.review_queue
    ADD CONSTRAINT review_queue_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (version);


--
-- Name: scrape_runs scrape_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_pkey PRIMARY KEY (id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: businesses_category_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX businesses_category_idx ON public.businesses USING btree (category);


--
-- Name: businesses_halal_status_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX businesses_halal_status_idx ON public.businesses USING btree (halal_status);


--
-- Name: businesses_muslim_owned_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX businesses_muslim_owned_idx ON public.businesses USING btree (muslim_owned);


--
-- Name: businesses_name_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX businesses_name_trgm ON public.businesses USING gin (name_normalized public.gin_trgm_ops);


--
-- Name: businesses_province_city_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX businesses_province_city_idx ON public.businesses USING btree (province, city);


--
-- Name: field_provenance field_provenance_business_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.field_provenance
    ADD CONSTRAINT field_provenance_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id) ON DELETE CASCADE;


--
-- Name: field_provenance field_provenance_listing_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.field_provenance
    ADD CONSTRAINT field_provenance_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.listings(id) ON DELETE CASCADE;


--
-- Name: listing_claims listing_claims_business_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listing_claims
    ADD CONSTRAINT listing_claims_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id) ON DELETE CASCADE;


--
-- Name: listings listings_business_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id) ON DELETE SET NULL;


--
-- Name: listings listings_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.listings
    ADD CONSTRAINT listings_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: removal_requests removal_requests_business_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.removal_requests
    ADD CONSTRAINT removal_requests_business_id_fkey FOREIGN KEY (business_id) REFERENCES public.businesses(id) ON DELETE CASCADE;


--
-- Name: scrape_runs scrape_runs_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scrape_runs
    ADD CONSTRAINT scrape_runs_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- PostgreSQL database dump complete
--

\unrestrict dbmate


--
-- Dbmate schema migrations
--

INSERT INTO public.schema_migrations (version) VALUES
    ('000'),
    ('001'),
    ('002');
