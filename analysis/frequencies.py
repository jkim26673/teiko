"""
analysis/frequencies.py | Part 2 Solution
-----------------------
Part 2: Cell-frequency summary table.

For each sample, computes the relative frequency of each immune cell
population as a percentage of the total cell count.
"""

import sqlite3
import pandas as pd
from analysis.db import CELL_TYPES

def _fetch_raw_counts(conn: sqlite3.Connection) -> pd.DataFrame:
    """Query DB — returns one row per sample with raw cell counts."""
    query = """
        SELECT
            s.sample_id  AS sample,
            cc.b_cell,
            cc.cd8_t_cell,
            cc.cd4_t_cell,
            cc.nk_cell,
            cc.monocyte
        FROM samples s
        JOIN cell_counts cc ON s.sample_id = cc.sample_id
    """
    return pd.read_sql_query(query, conn)

def _melt_to_frequencies(wide: pd.DataFrame) -> pd.DataFrame:
    """Convert wide cell-count DataFrame to long-format frequency table."""
    wide["total_count"] = wide[CELL_TYPES].sum(axis=1)
    rows = []
    for _, r in wide.iterrows():
        for pop in CELL_TYPES:
            rows.append({
                "sample":      r["sample"],
                "total_count": int(r["total_count"]),
                "population":  pop,
                "count":       int(r[pop]),
                "percentage":  round(r[pop] / r["total_count"] * 100, 4),
            })
    return pd.DataFrame(rows)

def compute_frequencies(conn: sqlite3.Connection) -> pd.DataFrame:
    """
    Return a long-format DataFrame with the relative frequency of each
    immune cell population for every sample.

    Columns: sample, total_count, population, count, percentage
    """
    wide = _fetch_raw_counts(conn)
    return _melt_to_frequencies(wide)
