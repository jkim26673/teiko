"""
analysis/db.py
--------------
Shared database connection and constants for the analysis package.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "clinical_trial.db")
CELL_TYPES = ["b_cell", "cd8_t_cell", "cd4_t_cell", "nk_cell", "monocyte"]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
