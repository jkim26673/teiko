# Part 4: Melanoma PBMC baseline subset analysis.
# Filters to melanoma patients on miraclib with PBMC samples at time=0.

import sqlite3
import pandas as pd

def fetch_baseline(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            sub.subject_id,
            sub.project_id,
            sub.response,
            sub.sex,
            s.sample_id
        FROM samples s
        JOIN subjects   sub ON s.subject_id    = sub.subject_id
        JOIN conditions c   ON sub.condition_id = c.condition_id
        JOIN treatments t   ON sub.treatment_id = t.treatment_id
        WHERE c.condition_name            = 'melanoma'
          AND t.treatment_name            = 'miraclib'
          AND s.sample_type               = 'PBMC'
          AND s.time_from_treatment_start = 0
    """
    return pd.read_sql_query(query, conn)


def count_by(df: pd.DataFrame, group_col: str, count_col: str, label: str) -> pd.DataFrame:
    return (
        df.groupby(group_col)[count_col]
        .count()
        .reset_index()
        .rename(columns={count_col: label})
    )


def avg_male_responder_b_cells(conn: sqlite3.Connection) -> float:
    query = """
        SELECT ROUND(AVG(cc.b_cell), 2) AS avg_b_cell
        FROM samples s
        JOIN subjects   sub ON s.subject_id    = sub.subject_id
        JOIN conditions c   ON sub.condition_id = c.condition_id
        JOIN treatments t   ON sub.treatment_id = t.treatment_id
        JOIN cell_counts cc ON s.sample_id      = cc.sample_id
        WHERE c.condition_name            = 'melanoma'
          AND t.treatment_name            = 'miraclib'
          AND s.sample_type               = 'PBMC'
          AND s.time_from_treatment_start = 0
          AND sub.sex                     = 'M'
          AND sub.response                = 'yes'
    """
    return conn.execute(query).fetchone()[0]


def melanoma_baseline_subset(conn: sqlite3.Connection):
    df       = fetch_baseline(conn)
    subjects = df.drop_duplicates("subject_id")

    by_project  = count_by(df,       "project_id", "sample_id",  "sample_count")
    by_response = count_by(subjects, "response",   "subject_id", "subject_count")
    by_sex      = count_by(subjects, "sex",        "subject_id", "subject_count")
    avg_b       = avg_male_responder_b_cells(conn)

    return by_project, by_response, by_sex, avg_b
