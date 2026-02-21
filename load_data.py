import csv
import sqlite3
import os
import logging

# Logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH  = os.path.join(os.path.dirname(__file__),"clinical_trial.db")
CSV_PATH = os.path.join(os.path.dirname(__file__),"cell-count.csv")


def get_schema():
    """
    Returns schema as a list of SQL statements.
    """
    return [
        "PRAGMA foreign_keys = ON;",

        # lookup tables
        "CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY);",
        "CREATE TABLE IF NOT EXISTS conditions (condition_id INTEGER PRIMARY KEY AUTOINCREMENT, condition_name TEXT NOT NULL UNIQUE);",
        "CREATE TABLE IF NOT EXISTS treatments (treatment_id INTEGER PRIMARY KEY AUTOINCREMENT, treatment_name TEXT NOT NULL UNIQUE);",

        #  entity tables
        """CREATE TABLE IF NOT EXISTS subjects (
            subject_id   TEXT PRIMARY KEY,
            project_id   TEXT    NOT NULL REFERENCES projects(project_id),
            condition_id INTEGER NOT NULL REFERENCES conditions(condition_id),
            treatment_id INTEGER NOT NULL REFERENCES treatments(treatment_id),
            age          INTEGER CHECK(age > 0 AND age < 150),
            sex          TEXT    CHECK(sex IN ('M', 'F', 'O')),
            response     TEXT    CHECK(response IN ('yes', 'no'))
        );""",

        # Samples
        """CREATE TABLE IF NOT EXISTS samples (
            sample_id                 TEXT PRIMARY KEY,
            subject_id                TEXT NOT NULL REFERENCES subjects(subject_id),
            sample_type               TEXT NOT NULL CHECK(sample_type IN ('PBMC', 'WB')),
            time_from_treatment_start INTEGER NOT NULL CHECK(time_from_treatment_start >= 0)
        );""",

        # separated cell measurements
        """CREATE TABLE IF NOT EXISTS cell_counts (
            sample_id   TEXT PRIMARY KEY REFERENCES samples(sample_id),
            b_cell      INTEGER NOT NULL,
            cd8_t_cell  INTEGER NOT NULL,
            cd4_t_cell  INTEGER NOT NULL,
            nk_cell     INTEGER NOT NULL,
            monocyte    INTEGER NOT NULL
        );""",

        # Index columns 
        "CREATE INDEX IF NOT EXISTS idx_subjects_project   ON subjects(project_id);",
        "CREATE INDEX IF NOT EXISTS idx_subjects_condition ON subjects(condition_id);",
        "CREATE INDEX IF NOT EXISTS idx_subjects_treatment ON subjects(treatment_id);",
        "CREATE INDEX IF NOT EXISTS idx_subjects_response  ON subjects(response);",
        "CREATE INDEX IF NOT EXISTS idx_subjects_sex       ON subjects(sex);",
        "CREATE INDEX IF NOT EXISTS idx_samples_subject    ON samples(subject_id);",
        "CREATE INDEX IF NOT EXISTS idx_samples_type_time  ON samples(sample_type, time_from_treatment_start);",
    ]



def init_db(conn):
    """Apply schema statements to the given connection."""
    logger.info("Initializing database schema...")
    cursor = conn.cursor()
    for statement in get_schema():
        try:
            cursor.execute(statement)
        except sqlite3.OperationalError as e:
            logger.warning(f"Schema statement skipped: {e}")


def load_csv(conn, csv_path):
    """Load all rows from csv_path into the already-initialized database."""
    cursor = conn.cursor()
    # Subjects appear once per sample in the CSV, so we track seen IDs too.
    condition_map = {}
    treatment_map = {}
    subject_seen  = set()
    skipped       = 0

    logger.info(f"Starting CSV ingest from {csv_path}...")

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)

        for row_idx, row in enumerate(reader, 1):
            try:
                # Project
                cursor.execute("INSERT OR IGNORE INTO projects(project_id) VALUES (?)", (row["project"],))

                #Condition 
                cond = row["condition"]
                if cond not in condition_map:
                    cursor.execute("INSERT OR IGNORE INTO conditions(condition_name) VALUES (?)", (cond,))
                    cursor.execute("SELECT condition_id FROM conditions WHERE condition_name = ?", (cond,))
                    condition_map[cond] = cursor.fetchone()[0]

                #Treatment 
                treat = row["treatment"]
                if treat not in treatment_map:
                    cursor.execute("INSERT OR IGNORE INTO treatments(treatment_name) VALUES (?)", (treat,))
                    cursor.execute("SELECT treatment_id FROM treatments WHERE treatment_name = ?", (treat,))
                    treatment_map[treat] = cursor.fetchone()[0]

                # Subject
                if row["subject"] not in subject_seen:
                    cursor.execute(
                        "INSERT OR IGNORE INTO subjects(subject_id, project_id, condition_id, treatment_id, age, sex, response) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            row["subject"],
                            row["project"],
                            condition_map[cond],
                            treatment_map[treat],
                            int(row["age"])    if row.get("age")      else None,
                            row["sex"]         if row.get("sex")       else None,
                            row["response"]    if row.get("response")  else None,
                        )
                    )
                    subject_seen.add(row["subject"])

                # Sample
                cursor.execute(
                    "INSERT OR IGNORE INTO samples(sample_id, subject_id, sample_type, time_from_treatment_start) VALUES (?, ?, ?, ?)",
                    (row["sample"], row["subject"], row["sample_type"], int(row["time_from_treatment_start"]))
                )

                # Cell counts
                cursor.execute(
                    "INSERT OR IGNORE INTO cell_counts(sample_id, b_cell, cd8_t_cell, cd4_t_cell, nk_cell, monocyte) VALUES (?, ?, ?, ?, ?, ?)",
                    (row["sample"], int(row["b_cell"]), int(row["cd8_t_cell"]), int(row["cd4_t_cell"]), int(row["nk_cell"]), int(row["monocyte"]))
                )
            except Exception as e:
                logger.warning(f"Row {row_idx}: skipping — {e}")
                skipped += 1

    conn.commit()

    if skipped:
        logger.warning(f"{skipped} rows skipped due to errors.")

    # sanity check
    logger.info("Load complete. Row counts:")
    for tbl in ("projects", "conditions", "treatments", "subjects", "samples", "cell_counts"):
        cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
        logger.info(f"  {tbl:<15} {cursor.fetchone()[0]:>6} rows")


def load_data():
    if not os.path.exists(CSV_PATH):
        logger.error(f"Could not find {CSV_PATH}. Make sure it's in the root directory.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        load_csv(conn, CSV_PATH)
    except Exception as e:
        logger.error(f"Failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    # remove existing DB 
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info(f"Removed existing {DB_PATH}")
    load_data()
