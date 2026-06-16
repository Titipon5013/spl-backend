-- Run against existing PostgreSQL DB after pulling Progress I changes
ALTER TABLE admins
    ADD COLUMN IF NOT EXISTS oauth_sub VARCHAR UNIQUE,
    ADD COLUMN IF NOT EXISTS auth_provider VARCHAR NOT NULL DEFAULT 'local',
    ADD COLUMN IF NOT EXISTS approval_status VARCHAR NOT NULL DEFAULT 'approved',
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP;

ALTER TABLE admins ALTER COLUMN hashed_password DROP NOT NULL;

UPDATE admins SET approval_status = 'approved', auth_provider = 'local' WHERE approval_status IS NULL;
