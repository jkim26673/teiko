"""
tests/test_load_data.py

Unit and integration tests for load_data.py.
Unit tests: test schema constraints using an in-memory DB.
Integration tests: load real CSV and verify row counts and data.
"""

import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import load_data


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
        self.assertEqual(tables, {"projects", "conditions", "treatments", "subjects", "samples", "cell_counts"})

    def _seed(self):
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
        self.conn.execute("INSERT INTO projects(project_id) VALUES ('prj1')")
        self.conn.execute("INSERT INTO conditions(condition_name) VALUES ('melanoma')")
        self.conn.execute("INSERT INTO treatments(treatment_name) VALUES ('miraclib')")
        with self.assertRaises(sqlite3.IntegrityError):
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
        # NULL response is valid — not all subjects have a known response
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
        distinct = self.conn.execute("SELECT COUNT(DISTINCT subject_id) FROM subjects").fetchone()[0]
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


if __name__ == "__main__":
    unittest.main()
