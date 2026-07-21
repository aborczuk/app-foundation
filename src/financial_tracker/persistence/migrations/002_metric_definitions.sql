SET search_path TO financial_tracker, public;

CREATE UNIQUE INDEX IF NOT EXISTS users_id_tenant_unique
    ON financial_tracker.users (id, tenant_id);

CREATE TABLE IF NOT EXISTS metric_definition_versions (
    tenant_id text NOT NULL,
    metric_id text NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    expression text NOT NULL,
    content_hash text NOT NULL,
    output_unit text NOT NULL,
    state text NOT NULL CHECK (state IN ('draft', 'active', 'retired', 'invalid')),
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, metric_id, version),
    CONSTRAINT metric_definition_creator_tenant_fk
        FOREIGN KEY (created_by, tenant_id)
        REFERENCES financial_tracker.users (id, tenant_id)
);
