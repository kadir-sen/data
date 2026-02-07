-- Initial database bootstrap
-- Runs once when the postgres volume is first created.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- RBAC tables (stubs — expand with Alembic migrations)
CREATE TABLE IF NOT EXISTS roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO roles (name) VALUES ('admin'), ('manager'), ('member')
ON CONFLICT (name) DO NOTHING;
