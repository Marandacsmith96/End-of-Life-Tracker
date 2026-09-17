-- Pet Quality-of-Life Tracker schema.
-- Every statement uses IF NOT EXISTS so this file can run on every start.

CREATE TABLE IF NOT EXISTS animals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    species     TEXT    NOT NULL CHECK (species IN ('cat', 'dog')),
    breed       TEXT,
    birth_date  DATE,
    photo_path  TEXT,
    archived    INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One entry per animal per day. Scores follow the HHHHHMM scale, 0-10 each.
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    entry_date  DATE    NOT NULL,
    hurt        INTEGER NOT NULL CHECK (hurt      BETWEEN 0 AND 10),
    hunger      INTEGER NOT NULL CHECK (hunger    BETWEEN 0 AND 10),
    hydration   INTEGER NOT NULL CHECK (hydration BETWEEN 0 AND 10),
    hygiene     INTEGER NOT NULL CHECK (hygiene   BETWEEN 0 AND 10),
    happiness   INTEGER NOT NULL CHECK (happiness BETWEEN 0 AND 10),
    mobility    INTEGER NOT NULL CHECK (mobility  BETWEEN 0 AND 10),
    good_days   INTEGER NOT NULL CHECK (good_days BETWEEN 0 AND 10),
    weight      REAL,
    weight_unit TEXT    CHECK (weight_unit IN ('kg', 'lb')),
    appetite    TEXT    CHECK (appetite IN ('none', 'low', 'normal', 'high')),
    notes       TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (animal_id, entry_date)
);

CREATE TABLE IF NOT EXISTS medications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    dose        TEXT,
    schedule    TEXT,
    active      INTEGER NOT NULL DEFAULT 1
);

-- Which medications were given on a given day.
CREATE TABLE IF NOT EXISTS entry_medications (
    entry_id      INTEGER NOT NULL REFERENCES entries(id)     ON DELETE CASCADE,
    medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
    given         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entry_id, medication_id)
);

CREATE TABLE IF NOT EXISTS photos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id    INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
    file_path   TEXT    NOT NULL,
    caption     TEXT
);

CREATE INDEX IF NOT EXISTS idx_entries_animal_date ON entries(animal_id, entry_date);
