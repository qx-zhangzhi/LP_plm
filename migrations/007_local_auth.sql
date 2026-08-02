ALTER TABLE members ADD COLUMN login_name TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN password_salt TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN password_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE members ADD COLUMN role_code TEXT NOT NULL DEFAULT 'designer';

CREATE UNIQUE INDEX IF NOT EXISTS members_login_name_idx ON members(login_name);
