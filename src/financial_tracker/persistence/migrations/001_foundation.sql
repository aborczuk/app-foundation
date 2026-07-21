CREATE SCHEMA IF NOT EXISTS financial_tracker;
SET search_path TO financial_tracker, public;

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    subject_id text NOT NULL,
    role text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT users_tenant_subject_unique UNIQUE (tenant_id, subject_id)
);

CREATE TABLE IF NOT EXISTS portfolios (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES users(id),
    name text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('watchlist', 'portfolio')),
    created_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_memberships (
    portfolio_id uuid NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    issuer_id uuid NOT NULL,
    added_at timestamptz NOT NULL,
    PRIMARY KEY (portfolio_id, issuer_id)
);

CREATE TABLE IF NOT EXISTS issuers (
    id uuid PRIMARY KEY,
    cik text NOT NULL,
    legal_name text NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT issuers_cik_unique UNIQUE (cik)
);

CREATE TABLE IF NOT EXISTS issuer_tickers (
    issuer_id uuid NOT NULL REFERENCES issuers(id) ON DELETE CASCADE,
    ticker text NOT NULL,
    exchange text,
    valid_from date NOT NULL,
    valid_to date,
    PRIMARY KEY (issuer_id, ticker, valid_from),
    CONSTRAINT issuer_tickers_date_order CHECK (valid_to IS NULL OR valid_to >= valid_from)
);

CREATE TABLE IF NOT EXISTS fiscal_periods (
    id uuid PRIMARY KEY,
    issuer_id uuid NOT NULL REFERENCES issuers(id),
    start_date date NOT NULL,
    end_date date NOT NULL,
    fiscal_year integer NOT NULL,
    fiscal_quarter smallint,
    period_kind text NOT NULL,
    CONSTRAINT fiscal_periods_date_order CHECK (end_date >= start_date),
    CONSTRAINT fiscal_periods_quarter_range CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4),
    CONSTRAINT fiscal_periods_identity_unique UNIQUE (issuer_id, start_date, end_date, period_kind)
);

CREATE TABLE IF NOT EXISTS filings (
    id uuid PRIMARY KEY,
    issuer_id uuid NOT NULL REFERENCES issuers(id),
    authority text NOT NULL,
    accession text NOT NULL,
    form_type text NOT NULL,
    filed_at timestamptz NOT NULL,
    accepted_at timestamptz,
    fiscal_period_id uuid REFERENCES fiscal_periods(id),
    is_amendment boolean NOT NULL,
    source_url text NOT NULL,
    supersedes_filing_id uuid REFERENCES filings(id),
    CONSTRAINT filings_authority_accession_unique UNIQUE (authority, accession),
    CONSTRAINT filings_no_self_supersession CHECK (supersedes_filing_id IS NULL OR supersedes_filing_id <> id)
);

CREATE TABLE IF NOT EXISTS financial_facts (
    id uuid PRIMARY KEY,
    issuer_id uuid NOT NULL REFERENCES issuers(id),
    filing_id uuid NOT NULL REFERENCES filings(id),
    fiscal_period_id uuid REFERENCES fiscal_periods(id),
    concept text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
    quality_state text NOT NULL CHECK (quality_state IN ('verified', 'derived', 'ambiguous', 'incomplete', 'stale', 'superseded', 'failed'))
);

CREATE UNIQUE INDEX IF NOT EXISTS financial_facts_identity_unique
    ON financial_facts (filing_id, concept, unit, COALESCE(fiscal_period_id, '00000000-0000-0000-0000-000000000000'::uuid), dimensions);

CREATE TABLE IF NOT EXISTS provenance (
    id uuid PRIMARY KEY,
    filing_id uuid NOT NULL REFERENCES filings(id),
    accession text NOT NULL,
    source_url text NOT NULL,
    selector text NOT NULL,
    captured_at timestamptz NOT NULL,
    source_fact_id uuid REFERENCES financial_facts(id),
    CONSTRAINT provenance_selector_unique UNIQUE (filing_id, selector, source_fact_id)
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    scope_hash text NOT NULL,
    definition_version_hash text NOT NULL,
    source_snapshot_hash text NOT NULL,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    created_at timestamptz NOT NULL,
    CONSTRAINT analysis_runs_identity_unique UNIQUE (tenant_id, scope_hash, definition_version_hash, source_snapshot_hash)
);

CREATE TABLE IF NOT EXISTS work_items (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    idempotency_key text NOT NULL,
    kind text NOT NULL,
    state text NOT NULL CHECK (state IN ('queued', 'leased', 'running', 'retry_wait', 'succeeded', 'dead_letter', 'cancelled')),
    lease_owner text,
    lease_expires_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    created_at timestamptz NOT NULL,
    CONSTRAINT work_items_idempotency_unique UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT work_items_lease_owner_required CHECK (state NOT IN ('leased', 'running') OR lease_owner IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    event_type text NOT NULL,
    idempotency_key text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT audit_events_identity_unique UNIQUE (tenant_id, event_type, idempotency_key)
);
