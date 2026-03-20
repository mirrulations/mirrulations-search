-- Migration 001: Replace upstream federal_register_documents with FR-native schema
-- Safe to run against DBs that have either the old or new shape

ALTER TABLE federal_register_documents
    DROP CONSTRAINT IF EXISTS federal_register_documents_pkey CASCADE;

ALTER TABLE federal_register_documents
    DROP COLUMN IF EXISTS docket_id,
    DROP COLUMN IF EXISTS fr_doc_num,
    DROP COLUMN IF EXISTS cfr_title,
    DROP COLUMN IF EXISTS cfr_part,
    ADD COLUMN IF NOT EXISTS document_number VARCHAR(50),
    ADD COLUMN IF NOT EXISTS abstract TEXT,
    ADD COLUMN IF NOT EXISTS publication_date DATE,
    ADD COLUMN IF NOT EXISTS effective_on DATE,
    ADD COLUMN IF NOT EXISTS docket_ids VARCHAR(50)[],
    ADD COLUMN IF NOT EXISTS agency_names TEXT[],
    ADD COLUMN IF NOT EXISTS topics TEXT[],
    ADD COLUMN IF NOT EXISTS significant BOOLEAN,
    ADD COLUMN IF NOT EXISTS regulation_id_numbers TEXT[],
    ADD COLUMN IF NOT EXISTS html_url VARCHAR(2000),
    ADD COLUMN IF NOT EXISTS pdf_url VARCHAR(2000),
    ADD COLUMN IF NOT EXISTS json_url VARCHAR(2000),
    ADD COLUMN IF NOT EXISTS start_page INTEGER,
    ADD COLUMN IF NOT EXISTS end_page INTEGER;

ALTER TABLE federal_register_documents
    ADD PRIMARY KEY (document_number);

ALTER TABLE federal_register_documents
    ALTER COLUMN document_id DROP NOT NULL,
    ALTER COLUMN agency_id DROP NOT NULL;

ALTER TABLE federal_register_documents DROP CONSTRAINT IF EXISTS federal_register_documents_document_id_fkey;

ALTER TABLE federal_register_documents ALTER COLUMN docket_ids TYPE TEXT[];

ALTER TABLE federal_register_cfr_parts ALTER COLUMN docket_id TYPE TEXT;

CREATE INDEX IF NOT EXISTS idx_federal_register_documents_docket_ids
    ON federal_register_documents USING GIN (docket_ids);

CREATE INDEX IF NOT EXISTS idx_federal_register_documents_publication_date
    ON federal_register_documents (publication_date);

CREATE TABLE IF NOT EXISTS federal_register_cfr_parts (
    document_number VARCHAR(50) NOT NULL
        REFERENCES federal_register_documents(document_number) ON DELETE CASCADE,
    docket_id VARCHAR(50) NOT NULL,
    cfr_title INTEGER NOT NULL,
    cfr_part VARCHAR(50) NOT NULL,
    citation_url VARCHAR(2000),
    PRIMARY KEY (document_number, docket_id, cfr_title, cfr_part)
);

CREATE INDEX IF NOT EXISTS idx_federal_register_cfr_parts_docket_id
    ON federal_register_cfr_parts (docket_id);

CREATE INDEX IF NOT EXISTS idx_federal_register_cfr_parts_cfr
    ON federal_register_cfr_parts (cfr_title, cfr_part);
