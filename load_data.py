"""
load_data.py

Initializes SQLite database and loads all rows from cell-count.csv.
Schema (normalized, 3NF):
  projects        - one row per project
  conditions      - lookup table for indication/condition
  treatments      - lookup table for treatment names
  subjects        - one row per patient (demographics + FK links)
  samples         - one row per biological sample
  cell_counts     - one row per sample's immune-cell records
"""

import csv
import os
import sqlite3

CSV_PATH = os.path.join(os.path.dirname(__file__), "cell-count.csv")
DB_PATH  = os.path.join(os.path.dirname(__file__), "clinical_trial.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Lookup / dimension tables

CREATE TABLE IF NOT EXISTS projects (
    project_id  TEXT PRIMARY KEY,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conditions (
    condition_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    condition_name TEXT NOT NULL UNIQUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS treatments (
    treatment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    treatment_name TEXT NOT NULL UNIQUE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Subject (patient) table

CREATE TABLE IF NOT EXISTS subjects (
    subject_id   TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(project_id),
    condition_id INTEGER NOT NULL REFERENCES conditions(condition_id),
    treatment_id INTEGER NOT NULL REFERENCES treatments(treatment_id),
    age          INTEGER CHECK(age > 0 AND age < 150),
    sex          TEXT CHECK(sex IN ('M','F','O')),
    response     TEXT CHECK(response IN ('yes','no')),
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Sample table

CREATE TABLE IF NOT EXISTS samples (
    sample_id                 TEXT PRIMARY KEY,
    subject_id                TEXT NOT NULL REFERENCES subjects(subject_id),
    sample_type               TEXT NOT NULL CHECK(sample_type IN ('PBMC', 'WB')),
    time_from_treatment_start INTEGER NOT NULL CHECK(time_from_treatment_start >= 0),
    created_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cell-count measurements

CREATE TABLE IF NOT EXISTS cell_counts (
    sample_id   TEXT PRIMARY KEY REFERENCES samples(sample_id),
    b_cell      INTEGER NOT NULL,
    cd8_t_cell  INTEGER NOT NULL,
    cd4_t_cell  INTEGER NOT NULL,
    nk_cell     INTEGER NOT NULL,
    monocyte    INTEGER NOT NULL,
    total_count INTEGER GENERATED ALWAYS AS (b_cell + cd8_t_cell + cd4_t_cell + nk_cell + monocyte) VIRTUAL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes: FK columns prevent full-table scans on every JOIN
CREATE INDEX IF NOT EXISTS idx_subjects_project   ON subjects(project_id);
CREATE INDEX IF NOT EXISTS idx_subjects_condition ON subjects(condition_id);
CREATE INDEX IF NOT EXISTS idx_subjects_treatment ON subjects(treatment_id);
CREATE INDEX IF NOT EXISTS idx_subjects_response  ON subjects(response);
CREATE INDEX IF NOT EXISTS idx_subjects_sex       ON subjects(sex);
CREATE INDEX IF NOT EXISTS idx_samples_subject    ON samples(subject_id);

-- Composite index: Parts 3 & 4 filter on both columns together
CREATE INDEX IF NOT EXISTS idx_samples_type_time ON samples(sample_type, time_from_treatment_start);

-- View: resolves FK integers to readable names so queries don't need explicit joins
CREATE VIEW IF NOT EXISTS subject_details AS
SELECT
    sub.subject_id,
    sub.project_id,
    c.condition_name,
    t.treatment_name,
    sub.age,
    sub.sex,
    sub.response
FROM subjects sub
JOIN conditions c ON sub.condition_id = c.condition_id
JOIN treatments t ON sub.treatment_id = t.treatment_id;
"""


# Helpers

def get_or_create(cursor, table, name_col, value):
    """Return the integer PK for a lookup-table row, inserting if needed."""
    cursor.execute(f"SELECT rowid FROM {table} WHERE {name_col} = ?", (value,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(f"INSERT INTO {table} ({name_col}) VALUES (?)", (value,))
    return cursor.lastrowid


def cached_lookup(cursor, cache, table, name_col, value):
    """Return cached FK id, calling get_or_create only on first encounter."""
    if value not in cache:
        cache[value] = get_or_create(cursor, table, name_col, value)
    return cache[value]


def insert_project(cursor, cache, project_id):
    if project_id not in cache:
        cursor.execute(
            "INSERT OR IGNORE INTO projects(project_id) VALUES (?)", (project_id,)
        )
        cache[project_id] = True


def insert_subject(cursor, seen, row, condition_id, treatment_id):
    subject_id = row["subject"]
    if subject_id not in seen:
        cursor.execute(
            """
            INSERT OR IGNORE INTO subjects
                (subject_id, project_id, condition_id, treatment_id,
                 age, sex, response)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject_id,
                row["project"],
                condition_id,
                treatment_id,
                int(row["age"])  if row["age"]     else None,
                row["sex"]       if row["sex"]      else None,
                row["response"]  if row["response"] else None,
            )
        )
        seen.add(subject_id)


def insert_sample(cursor, row):
    cursor.execute(
        """
        INSERT OR IGNORE INTO samples
            (sample_id, subject_id, sample_type, time_from_treatment_start)
        VALUES (?, ?, ?, ?)
        """,
        (
            row["sample"],
            row["subject"],
            row["sample_type"],
            int(row["time_from_treatment_start"]),
        )
    )


def insert_cell_counts(cursor, row):
    cursor.execute(
        """
        INSERT OR IGNORE INTO cell_counts
            (sample_id, b_cell, cd8_t_cell, cd4_t_cell, nk_cell, monocyte)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            row["sample"],
            int(row["b_cell"]),
            int(row["cd8_t_cell"]),
            int(row["cd4_t_cell"]),
            int(row["nk_cell"]),
            int(row["monocyte"]),
        )
    )


# Main loader

def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def load_csv(conn, csv_path):
    cur = conn.cursor()
    project_cache   = {}
    condition_cache = {}
    treatment_cache = {}
    subject_seen    = set()

    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            insert_project(cur, project_cache, row["project"])
            condition_id = cached_lookup(cur, condition_cache, "conditions", "condition_name", row["condition"])
            treatment_id = cached_lookup(cur, treatment_cache, "treatments", "treatment_name", row["treatment"])
            insert_subject(cur, subject_seen, row, condition_id, treatment_id)
            insert_sample(cur, row)
            insert_cell_counts(cur, row)

    conn.commit()
    print(f"Database written to: {DB_PATH}")

    for tbl in ("projects", "conditions", "treatments", "subjects", "samples", "cell_counts"):
        cur.execute(f"SELECT COUNT(*) FROM {tbl}")
        print(f"  {tbl:<15} {cur.fetchone()[0]:>6} rows")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        load_csv(conn, CSV_PATH)
    finally:
        conn.close()
