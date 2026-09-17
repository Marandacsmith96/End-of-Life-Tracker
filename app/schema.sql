-- Pet Quality-of-Life Tracker schema (version 2).
-- Every statement uses IF NOT EXISTS so this file can run on every start.
-- Existing databases are upgraded by the migrations in db.py.

CREATE TABLE IF NOT EXISTS animals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    species       TEXT    NOT NULL CHECK (species IN ('cat', 'dog')),
    breed         TEXT,
    sex           TEXT    CHECK (sex IN ('female', 'male', 'unknown')),
    birth_date    DATE,
    photo_path    TEXT,
    diagnoses     TEXT,
    status        TEXT    NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'passed')),
    passed_date   DATE,
    reminder      TEXT    NOT NULL DEFAULT 'daily' CHECK (reminder IN ('off', 'daily', 'every_other_day', 'weekly')),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One entry per animal per day. day_status is the single most important field;
-- the HHHHHMM scores are optional so a quick check-in still counts.
CREATE TABLE IF NOT EXISTS entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    entry_date  DATE    NOT NULL,
    day_status  TEXT    CHECK (day_status IN ('good', 'bad', 'mixed')),
    hurt        INTEGER CHECK (hurt      BETWEEN 0 AND 10),
    hunger      INTEGER CHECK (hunger    BETWEEN 0 AND 10),
    hydration   INTEGER CHECK (hydration BETWEEN 0 AND 10),
    hygiene     INTEGER CHECK (hygiene   BETWEEN 0 AND 10),
    happiness   INTEGER CHECK (happiness BETWEEN 0 AND 10),
    mobility    INTEGER CHECK (mobility  BETWEEN 0 AND 10),
    good_days   INTEGER CHECK (good_days BETWEEN 0 AND 10),
    weight      REAL,
    weight_unit TEXT    CHECK (weight_unit IN ('kg', 'lb')),
    appetite    TEXT    CHECK (appetite IN ('none', 'low', 'normal', 'high')),
    notes       TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (animal_id, entry_date)
);
CREATE INDEX IF NOT EXISTS idx_entries_animal_date ON entries(animal_id, entry_date);

-- "What does a good day look like?" Three to five behaviors per animal.
CREATE TABLE IF NOT EXISTS personal_markers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    label       TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_markers_animal ON personal_markers(animal_id);

CREATE TABLE IF NOT EXISTS marker_responses (
    entry_id    INTEGER NOT NULL REFERENCES entries(id)          ON DELETE CASCADE,
    marker_id   INTEGER NOT NULL REFERENCES personal_markers(id) ON DELETE CASCADE,
    completed   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (entry_id, marker_id)
);

-- Owner-estimated reference point ("about six months ago"). Never mixed with
-- measured entries; shown as a labelled reference line.
CREATE TABLE IF NOT EXISTS baselines (
    animal_id        INTEGER PRIMARY KEY REFERENCES animals(id) ON DELETE CASCADE,
    approximate_date DATE,
    hurt        INTEGER CHECK (hurt      BETWEEN 0 AND 10),
    hunger      INTEGER CHECK (hunger    BETWEEN 0 AND 10),
    hydration   INTEGER CHECK (hydration BETWEEN 0 AND 10),
    hygiene     INTEGER CHECK (hygiene   BETWEEN 0 AND 10),
    happiness   INTEGER CHECK (happiness BETWEEN 0 AND 10),
    mobility    INTEGER CHECK (mobility  BETWEEN 0 AND 10),
    good_days   INTEGER CHECK (good_days BETWEEN 0 AND 10),
    good_day_pattern TEXT CHECK (good_day_pattern IN ('mostly_good', 'mixed', 'mostly_bad')),
    marker_frequency TEXT CHECK (marker_frequency IN ('most_days', 'some_days', 'rarely')),
    notes       TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS medications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    name        TEXT    NOT NULL,
    dose        TEXT,
    schedule    TEXT,
    start_date  DATE,
    end_date    DATE,
    active      INTEGER NOT NULL DEFAULT 1
);

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

-- Timeline events: vet visits, medication changes, procedures, and so on.
CREATE TABLE IF NOT EXISTS pet_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    event_date  DATE    NOT NULL,
    type        TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    note        TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_events_animal_date ON pet_events(animal_id, event_date);

-- Weekly "how are you doing?" for the caregiver. Kept entirely separate from
-- the animal's scores.
CREATE TABLE IF NOT EXISTS caregiver_checkins (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    animal_id   INTEGER NOT NULL REFERENCES animals(id) ON DELETE CASCADE,
    checkin_date DATE   NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('okay', 'harder', 'exhausted', 'overwhelmed')),
    note        TEXT,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_caregiver_animal_date ON caregiver_checkins(animal_id, checkin_date);
