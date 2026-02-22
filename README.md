# Teiko Miraclib Immune Cell Analysis Dashboard

The goal of this project is to observe the effect of **miraclib** on immune cell populations in melanoma patients, comparing treatment responders and non-responders using PBMC cell count data collected over a 14-day treatment window (days 0, 7, 14).

**Live dashboard:** https://teiko-1.onrender.com

---

## Setup (GitHub Codespaces)

```bash
pip install -r requirements.txt
python load_data.py        # builds clinical_trial.db from cell-count.csv
python run_part2.py        # cell frequency summary
python run_part3.py        # GEE responder comparison + boxplot
python run_part4.py        # baseline subset counts
python run_dashboard.py    # launch dashboard
```

Tests:

```bash
python -m unittest tests/test_analysis.py -v
```

---

## Database Schema

Six tables in third normal form (3NF):

```
projects    (project_id)
conditions  (condition_id, condition_name)
treatments  (treatment_id, treatment_name)
subjects    (subject_id, project_id, condition_id, treatment_id, age, sex, response)
samples     (sample_id, subject_id, sample_type, time_from_treatment_start)
cell_counts (sample_id, b_cell, cd8_t_cell, cd4_t_cell, nk_cell, monocyte)
```

**Why this design?**

Condition names and treatment names are stored once in lookup tables (`conditions`, `treatments`) and referenced by integer foreign key in `subjects`. I did this to avoid storing repeated strings like `"melanoma"` or `"miraclib"` across thousands of subject rows. This keeps updates atomic and makes filtering by condition or treatment efficient via JOIN rather than a full-table string scan.

`subjects` and `samples` are separated because a subject is a person and a sample is a biological specimen (this is a one-to-many relationship). `cell_counts` is separated from `samples` because it holds measurement data, and using `sample_id` as primary key enforces that each sample has exactly one set of counts.

Indexes are placed on the columns most commonly used in WHERE clauses and JOINs: `project_id`, `condition_id`, `treatment_id`, `response`, `sex`, `subject_id`, and `(sample_type, time_from_treatment_start)`.

**How this scales:**

- *Hundreds of projects* : each is one row in `projects`. Queries filter by `project_id` using the existing index. Cross-project comparisons can be made using GROUP BY .
- *Thousands of samples* : the normalized schema keeps row sizes small. The compound index on `(sample_type, time_from_treatment_start)` covers the most common filter combination.
- *New conditions or treatments* : you can just add an INSERT into a lookup table with no schema change needed.
- *New cell types* : the current `cell_counts` table uses fixed columns, which is efficient for a known fixed panel. If the panel varied across projects, `cell_counts` could be redesigned as a long-format table `(sample_id, cell_type, count)` at the cost of some query complexity.
- *Various analytics* : the normalized schema supports arbitrary JOINs: time-series per subject, cross-project cohort comparisons, subgroup filtering by sex/age/response, and aggregation at any level.

---

## Code Structure

```
teiko/
├── load_data.py              # Part 1: build clinical_trial.db from cell-count.csv
├── analysis/
│   ├── db.py                 # shared DB path, connection helper, CELL_TYPES constant
│   ├── frequencies.py        # Part 2: relative frequencies per sample
│   ├── statistics.py         # Part 3: GEE responder vs non-responder comparison
│   ├── subset.py             # Part 4: melanoma PBMC baseline subset counts
│   └── EDA.ipynb             # Part 3 GEE statistical analysis, exploratory analysis and model validation
├── run_part2.py              # print frequency summary + histogram
├── run_part3.py              # print GEE results + boxplot
├── run_part4.py              # print baseline subset counts
├── run_dashboard.py          # launch interactive dashboard
├── dashboard_app.py          # Plotly Dash app (5 tabs)
├── tests/
│   └── test_analysis.py      # unit tests  + integration tests
├── cell-count.csv            # source data
└── requirements.txt
```

**Design rationale:**

The `analysis/` directory is a Python package so all run scripts and the dashboard import from the same folder. Each part of the analysis lives in its own module.

`db.py` centralizes the DB path and the `CELL_TYPES` list. Having `CELL_TYPES` in one place means adding or renaming a population requires a change in exactly one file, and both the analysis functions and tests stay in sync automatically.

The run scripts are thin wrappers that call the analysis functions, print results, and show plots. The dashboard calls the same functions, so both paths always reflect the same underlying logic.

---

## Analysis Summary

**Part 2:** Relative frequencies computed as each population's raw count divided by the total across all 5 populations per sample.

**Part 3:** Each subject contributes 3 repeated PBMC samples (days 0, 7, 14), which violates the independence assumption of standard tests. GEE with exchangeable working correlation was used to model population-averaged effects while accounting for within-subject clustering.

Model: `percentage ~ response * time + sex + age + C(project_id)`

BH FDR correction was applied across 10 tests (5 populations x 2 terms: main effect at baseline + response-by-time interaction). No cell population shows a statistically significant difference at baseline between responders and non-responders. CD4 T cells show a interesting divergence by day 7 (+0.65 pp, derived from the interaction term). B cell trajectories show a nominally significant differential decline in responders (p = 0.016) that does not survive FDR correction (p_adj = 0.164). I also noticed not much in-clustering correlation.

**Part 4:** 656 melanoma patients on miraclib with PBMC samples at baseline: 384 from prj1, 272 from prj3. 331 responders, 325 non-responders. 344 male, 312 female. Average B cell count in male responders at baseline: 10401.28.

---

## Dashboard Features

- Overview tab: subject counts, responder/non-responder split, median frequency bar chart
- Cell Population Comparison: toggle all time points vs baseline only, time trend lines (mean +/- SEM) per population, GEE results table with FDR-adjusted p-values
- Baseline Subset: sample and subject counts by project, response, and sex
- Data Overview: frequency distribution histogram, sortable and filterable sample table
- Methods: model specification, design rationale, key findings
