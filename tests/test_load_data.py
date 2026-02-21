"""
tests/test_load_data.py

Unit and integration tests for load_data.py.

Unit tests (TestSchema):
    Use an in-memory SQLite database ; no CSV required.
    Tests schema structure, constraints, and helper functions.

Integration tests (TestLoadCSV):
    Loads the real cell-count.csv into an in-memory database.
    Tests row counts, data integrity, and foreign key relationships.

Run:
    python -m unittest discover -v -s tests -p "test_*.py"
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import load_data


# Unit tests — in-memory DB, no CSV

class TestSchema(unittest.TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON")
        load_data.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_all_tables_created(self):
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = {row[0] for row in cur.fetchall()}
        expected = {"projects", "conditions", "treatments", "subjects", "samples", "cell_counts"}
        self.assertEqual(tables, expected)

    def test_indexes_created(self):
        cur = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row[0] for row in cur.fetchall()}
        for expected in [
            "idx_subjects_project",
            "idx_subjects_condition",
            "idx_subjects_treatment",
            "idx_subjects_response",
            "idx_subjects_sex",
            "idx_samples_subject",
            "idx_samples_type_time",
        ]:
            self.assertIn(expected, indexes)

    def test_get_or_create_inserts_new(self):
        cur = self.conn.cursor()
        pk = load_data.get_or_create(cur, "conditions", "condition_name", "melanoma")
        self.assertIsNotNone(pk)

    def test_get_or_create_returns_same_id(self):
        cur = self.conn.cursor()
        id1 = load_data.get_or_create(cur, "conditions", "condition_name", "melanoma")
        id2 = load_data.get_or_create(cur, "conditions", "condition_name", "melanoma")
        self.assertEqual(id1, id2)

    # Constraint tests 

    def _seed(self):
        """Insert the minimum rows needed to test sample/subject constraints."""
        self.conn.execute("INSERT INTO projects(project_id) VALUES ('prj1')")
        self.conn.execute("INSERT INTO conditions(condition_name) VALUES ('melanoma')")
        self.conn.execute("INSERT INTO treatments(treatment_name) VALUES ('miraclib')")
        self.conn.execute(
            "INSERT INTO subjects(subject_id, project_id, condition_id, treatment_id, age, sex) "
            "VALUES ('sbj000', 'prj1', 1, 1, 57, 'M')"
        )

    def test_sample_type_rejects_invalid(self):
        self._seed()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO samples(sample_id, subject_id, sample_type, time_from_treatment_start) "
                "VALUES ('s1', 'sbj000', 'BLOOD', 0)"
            )

    def test_response_rejects_invalid(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO projects(project_id) VALUES ('prj1')")
            self.conn.execute(
                "INSERT INTO conditions(condition_name) VALUES ('melanoma')")
            self.conn.execute(
                "INSERT INTO treatments(treatment_name) VALUES ('miraclib')")
            self.conn.execute(
                "INSERT INTO subjects(subject_id, project_id, condition_id, treatment_id, response) "
                "VALUES ('sbj999', 'prj1', 1, 1, 'maybe')"
            )

    def test_age_rejects_out_of_range(self):
        self.conn.execute("INSERT INTO projects(project_id) VALUES ('prj1')")
        self.conn.execute("INSERT INTO conditions(condition_name) VALUES ('melanoma')")
        self.conn.execute("INSERT INTO treatments(treatment_name) VALUES ('miraclib')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO subjects(subject_id, project_id, condition_id, treatment_id, age) "
                "VALUES ('sbj999', 'prj1', 1, 1, 200)"
            )

    def test_null_response_allowed(self):
        self._seed()
        # Should not raise — NULL response is valid for non-melanoma patients
        self.conn.execute(
            "INSERT INTO subjects(subject_id, project_id, condition_id, treatment_id, response) "
            "VALUES ('sbj_healthy', 'prj1', 1, 1, NULL)"
        )

    def test_time_from_treatment_start_rejects_negative(self):
        self._seed()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO samples(sample_id, subject_id, sample_type, time_from_treatment_start) "
                "VALUES ('s1', 'sbj000', 'PBMC', -1)"
            )


# Integration tests — loads real CSV

class TestLoadCSV(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.execute("PRAGMA foreign_keys = ON")
        load_data.init_db(cls.conn)
        load_data.load_csv(cls.conn, load_data.CSV_PATH)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def _count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_row_counts(self):
        self.assertEqual(self._count("projects"), 3)
        self.assertEqual(self._count("conditions"), 3)
        self.assertEqual(self._count("treatments"), 3)
        self.assertEqual(self._count("subjects"), 3500)
        self.assertEqual(self._count("samples"), 10500)
        self.assertEqual(self._count("cell_counts"), 10500)

    def test_no_duplicate_subjects(self):
        total = self._count("subjects")
        distinct = self.conn.execute(
            "SELECT COUNT(DISTINCT subject_id) FROM subjects"
        ).fetchone()[0]
        self.assertEqual(total, distinct)

    def test_subject_sbj000_spot_check(self):
        row = self.conn.execute("""
            SELECT sub.subject_id, c.condition_name, t.treatment_name,
                   sub.response, sub.sex, sub.age
            FROM subjects sub
            JOIN conditions c ON sub.condition_id = c.condition_id
            JOIN treatments t ON sub.treatment_id = t.treatment_id
            WHERE sub.subject_id = 'sbj000'
        """).fetchone()
        self.assertEqual(row[0], "sbj000")
        self.assertEqual(row[1], "melanoma")
        self.assertEqual(row[2], "miraclib")
        self.assertEqual(row[3], "no")
        self.assertEqual(row[4], "M")
        self.assertEqual(row[5], 57)

    def test_sbj000_has_three_time_points(self):
        rows = self.conn.execute(
            "SELECT time_from_treatment_start FROM samples "
            "WHERE subject_id = 'sbj000' ORDER BY time_from_treatment_start"
        ).fetchall()
        self.assertEqual([r[0] for r in rows], [0, 7, 14])

    def test_no_orphaned_samples(self):
        count = self.conn.execute("""
            SELECT COUNT(*) FROM samples s
            LEFT JOIN subjects sub ON s.subject_id = sub.subject_id
            WHERE sub.subject_id IS NULL
        """).fetchone()[0]
        self.assertEqual(count, 0)

    def test_no_orphaned_cell_counts(self):
        count = self.conn.execute("""
            SELECT COUNT(*) FROM cell_counts cc
            LEFT JOIN samples s ON cc.sample_id = s.sample_id
            WHERE s.sample_id IS NULL
        """).fetchone()[0]
        self.assertEqual(count, 0)

    def test_cell_counts_non_negative(self):
        count = self.conn.execute("""
            SELECT COUNT(*) FROM cell_counts
            WHERE b_cell < 0 OR cd8_t_cell < 0 OR cd4_t_cell < 0
               OR nk_cell < 0 OR monocyte < 0
        """).fetchone()[0]
        self.assertEqual(count, 0)

    def test_total_count_matches_generated_column(self):
        row = self.conn.execute("""
            SELECT b_cell + cd8_t_cell + cd4_t_cell + nk_cell + monocyte,
                   total_count
            FROM cell_counts
            WHERE sample_id = 'sample00000'
        """).fetchone()
        self.assertEqual(row[0], row[1])


if __name__ == "__main__":
    unittest.main()
