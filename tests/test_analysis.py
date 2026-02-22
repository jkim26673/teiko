# tests/test_analysis.py
# Unit and integration tests for the analysis package (Parts 2, 3, 4).
# Unit tests use in-memory SQLite DB.
# Integration tests run against the clinical_trial.db.

import os
import sqlite3
import unittest

from analysis.frequencies import compute_frequencies
from analysis.statistics  import compare_responders
from analysis.subset      import melanoma_baseline_subset
from analysis.db          import CELL_TYPES, get_connection, DB_PATH


def make_db():
    """
    Subjects (all melanoma + miraclib):
      subj1  prj1  M  yes
      subj2  prj1  M  yes
      subj3  prj1  F  yes
      subj4  prj1  M  no
      subj5  prj1  M  no
      subj6  prj1  F  no
      subj7  prj2  M  yes  (second project)
      subj8  prj1  M  NULL healthy (excluded from Part 3/4)

    Samples (all PBMC at time=0):
      smp01-07: PBMC, time=0  (baseline cohort)
      smp08:    WB,   time=0  (excluded - not PBMC)
      smp09:    PBMC, time=1  (excluded from Part 4 - not baseline)
      smp10:    PBMC, time=0  (excluded - healthy subject)

    Cell counts (all totals = 500):
      smp01: b=100  → 20%    smp04: b=300 → 60%
      smp02: b=200  → 40%    smp05: b=250 → 50%
      smp03: b=50   → 10%    smp06: b=150 → 30%
      smp07: b=300  → 60%

    Avg B cells for male responders at baseline: (100+200+300)/3 = 200.00
    Part 4 by_project: prj1=6, prj2=1
    Part 4 by_response: yes=4, no=3
    Part 4 by_sex: M=5, F=2
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE projects (project_id TEXT PRIMARY KEY);
        CREATE TABLE conditions (condition_id INTEGER PRIMARY KEY AUTOINCREMENT, condition_name TEXT UNIQUE NOT NULL);
        CREATE TABLE treatments (treatment_id INTEGER PRIMARY KEY AUTOINCREMENT, treatment_name TEXT UNIQUE NOT NULL);
        CREATE TABLE subjects (
            subject_id TEXT PRIMARY KEY, project_id TEXT NOT NULL,
            condition_id INTEGER NOT NULL, treatment_id INTEGER NOT NULL,
            response TEXT, sex TEXT, age INTEGER
        );
        CREATE TABLE samples (
            sample_id TEXT PRIMARY KEY, subject_id TEXT NOT NULL,
            sample_type TEXT NOT NULL, time_from_treatment_start INTEGER NOT NULL
        );
        CREATE TABLE cell_counts (
            sample_id TEXT PRIMARY KEY, b_cell INTEGER NOT NULL,
            cd8_t_cell INTEGER NOT NULL, cd4_t_cell INTEGER NOT NULL,
            nk_cell INTEGER NOT NULL, monocyte INTEGER NOT NULL
        );
    """)
    conn.execute("INSERT INTO projects VALUES ('prj1'), ('prj2')")
    conn.execute("INSERT INTO conditions (condition_name) VALUES ('melanoma'), ('healthy')")
    conn.execute("INSERT INTO treatments (treatment_name) VALUES ('miraclib'), ('placebo')")
    conn.execute("""INSERT INTO subjects VALUES
        ('subj1','prj1',1,1,'yes','M',45), ('subj2','prj1',1,1,'yes','M',52),
        ('subj3','prj1',1,1,'yes','F',38), ('subj4','prj1',1,1,'no','M',60),
        ('subj5','prj1',1,1,'no','M',55),  ('subj6','prj1',1,1,'no','F',47),
        ('subj7','prj2',1,1,'yes','M',50), ('subj8','prj1',2,1,NULL,'M',40)
    """)
    conn.execute("""INSERT INTO samples VALUES
        ('smp01','subj1','PBMC',0), ('smp02','subj2','PBMC',0),
        ('smp03','subj3','PBMC',0), ('smp04','subj4','PBMC',0),
        ('smp05','subj5','PBMC',0), ('smp06','subj6','PBMC',0),
        ('smp07','subj7','PBMC',0), ('smp08','subj1','WB',0),
        ('smp09','subj1','PBMC',1), ('smp10','subj8','PBMC',0)
    """)
    conn.execute("""INSERT INTO cell_counts VALUES
        ('smp01',100, 50,200, 25,125), ('smp02',200,100,100, 50, 50),
        ('smp03', 50,150,150, 75, 75), ('smp04',300, 50, 50, 25, 75),
        ('smp05',250, 75, 75, 50, 50), ('smp06',150,100,100,100, 50),
        ('smp07',300, 50,100, 25, 25), ('smp08', 10, 20, 30, 15, 25),
        ('smp09', 80, 60,150,150, 60), ('smp10',200,100,100, 50, 50)
    """)
    conn.commit()
    return conn


# Part 2
class TestComputeFrequencies(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_shape(self):
        freq = compute_frequencies(self.conn)
        self.assertEqual(freq.shape, (50, 5)) 

    def test_percentages_sum_to_100(self):
        freq = compute_frequencies(self.conn)
        for sample in freq["sample"].unique():
            total = freq[freq["sample"] == sample]["percentage"].sum()
            self.assertAlmostEqual(total, 100.0, places=2)

    def test_percentage_value(self):
        freq = compute_frequencies(self.conn)
        pct = freq[(freq["sample"] == "smp01") & (freq["population"] == "b_cell")]["percentage"].iloc[0]
        self.assertAlmostEqual(pct, 20.0, places=4)


#Part 3

class TestCompareResponders(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_returns_two_dataframes(self):
        freq_df, stats_df = compare_responders(self.conn)
        self.assertEqual(len(freq_df.columns), 9)
        self.assertEqual(len(stats_df), 5)

    def test_stats_has_one_row_per_population(self):
        _, stats_df = compare_responders(self.conn)
        self.assertEqual(list(stats_df["population"]), CELL_TYPES)

    def test_p_values_valid(self):
        _, stats_df = compare_responders(self.conn)
        self.assertTrue((stats_df["p_response"] >= 0).all())
        self.assertTrue((stats_df["p_response"] <= 1).all())


#Part 4 

class TestMelanomaBaselineSubset(unittest.TestCase):

    def setUp(self):
        self.conn = make_db()

    def tearDown(self):
        self.conn.close()

    def test_sample_count_by_project(self):
        by_project, _, _, _ = melanoma_baseline_subset(self.conn)
        counts = dict(zip(by_project["project_id"], by_project["sample_count"]))
        self.assertEqual(counts["prj1"], 6)
        self.assertEqual(counts["prj2"], 1)

    def test_subject_count_by_response(self):
        _, by_response, _, _ = melanoma_baseline_subset(self.conn)
        counts = dict(zip(by_response["response"], by_response["subject_count"]))
        self.assertEqual(counts["yes"], 4)
        self.assertEqual(counts["no"],  3)

    def test_subject_count_by_sex(self):
        _, _, by_sex, _ = melanoma_baseline_subset(self.conn)
        counts = dict(zip(by_sex["sex"], by_sex["subject_count"]))
        self.assertEqual(counts["M"], 5)
        self.assertEqual(counts["F"], 2)

    def test_avg_male_responder_b_cells(self):
        _, _, _, avg_b = melanoma_baseline_subset(self.conn)
        self.assertAlmostEqual(avg_b, 200.00, places=2)


# Integration tests:

@unittest.skipUnless(os.path.exists(DB_PATH), "clinical_trial.db not found")
class TestPart2Integration(unittest.TestCase):

    def setUp(self):
        self.conn = get_connection()

    def tearDown(self):
        self.conn.close()

    def test_shape(self):
        self.assertEqual(compute_frequencies(self.conn).shape, (52500, 5))

    def test_percentages_sum_to_100(self):
        freq = compute_frequencies(self.conn)
        totals = freq.groupby("sample")["percentage"].sum()
        self.assertTrue((totals - 100.0).abs().lt(0.01).all())


@unittest.skipUnless(os.path.exists(DB_PATH), "clinical_trial.db not found")
class TestPart3Integration(unittest.TestCase):

    def setUp(self):
        self.conn = get_connection()

    def tearDown(self):
        self.conn.close()

    def test_five_populations(self):
        _, stats_df = compare_responders(self.conn)
        self.assertEqual(list(stats_df["population"]), CELL_TYPES)

    def test_no_population_significant_after_correction(self):
        _, stats_df = compare_responders(self.conn)
        self.assertFalse(stats_df["sig_response"].any())


@unittest.skipUnless(os.path.exists(DB_PATH), "clinical_trial.db not found")
class TestPart4Integration(unittest.TestCase):

    def setUp(self):
        self.conn = get_connection()

    def tearDown(self):
        self.conn.close()

    def test_sample_counts_by_project(self):
        by_project, _, _, _ = melanoma_baseline_subset(self.conn)
        counts = dict(zip(by_project["project_id"], by_project["sample_count"]))
        self.assertEqual(counts["prj1"], 384)
        self.assertEqual(counts["prj3"], 272)

    def test_avg_male_responder_b_cells(self):
        _, _, _, avg_b = melanoma_baseline_subset(self.conn)
        self.assertAlmostEqual(avg_b, 10401.28, places=2)


if __name__ == "__main__":
    unittest.main()
