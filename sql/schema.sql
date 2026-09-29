-- Uživatelé (obchodníci a vedoucí)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('sales', 'manager')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Poptávky
CREATE TABLE leads (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    message TEXT,
    source TEXT NOT NULL CHECK (source IN ('web', 'meta', 'email', 'referral', 'manual')),
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'contacted', 'offer', 'won', 'lost')),
    assigned_to INT REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    first_response_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Historie aktivit u poptávek
CREATE TABLE activities (
    id SERIAL PRIMARY KEY,
    lead_id INT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    user_id INT REFERENCES users(id),
    type TEXT NOT NULL
        CHECK (type IN ('created', 'assigned', 'status_change', 'call', 'email', 'meeting', 'note')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
