-- rag_patterns: catalog of the four Project A RAG patterns from the Excel worksheet
-- 1_Project_A_Healthcare_Content (row 9 "Patterns from SKILL.md").
-- pattern_key is the slug used by API callers; display_name is the human label;
-- summary is the short rationale from the Excel.

CREATE TABLE rag_patterns (
    id            BIGSERIAL    PRIMARY KEY,
    pattern_key   VARCHAR(100) NOT NULL UNIQUE,
    display_name  VARCHAR(200) NOT NULL,
    summary       TEXT         NOT NULL,
    excel_source  VARCHAR(300),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_dt    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_dt    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_rag_patterns_pattern_key
        CHECK (pattern_key ~ '^[a-z0-9_]+$')
);

CREATE INDEX idx_rag_patterns_is_active ON rag_patterns (is_active);

COMMENT ON COLUMN rag_patterns.pattern_key  IS 'Slug used in API URLs and as the FK target. [a-z0-9_] only.';
COMMENT ON COLUMN rag_patterns.excel_source IS 'Provenance — which Excel row/cell this pattern was sourced from.';
