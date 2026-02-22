# Part 3: Responder vs non-responder comparison.
# Cohort: melanoma patients on miraclib, PBMC samples only.
# Each subject has 3 repeated measures (day 0, 7, 14) — independence is violated
# for Mann-Whitney/t-test. We use GEE with exchangeable correlation instead.

import sqlite3
import pandas as pd
from statsmodels.genmod.generalized_estimating_equations import GEE
from statsmodels.genmod.families import Gaussian
from statsmodels.genmod.cov_struct import Exchangeable
from statsmodels.stats.multitest import multipletests
from analysis.db import CELL_TYPES


def fetch_cohort(conn: sqlite3.Connection) -> pd.DataFrame:
    query = """
        SELECT
            s.sample_id                 AS sample,
            sub.subject_id,
            sub.response,
            sub.sex,
            sub.age,
            sub.project_id,
            s.time_from_treatment_start AS time,
            cc.b_cell,
            cc.cd8_t_cell,
            cc.cd4_t_cell,
            cc.nk_cell,
            cc.monocyte
        FROM samples s
        JOIN subjects    sub ON s.subject_id    = sub.subject_id
        JOIN conditions  c   ON sub.condition_id = c.condition_id
        JOIN treatments  t   ON sub.treatment_id = t.treatment_id
        JOIN cell_counts cc  ON s.sample_id      = cc.sample_id
        WHERE c.condition_name = 'melanoma'
          AND t.treatment_name = 'miraclib'
          AND s.sample_type    = 'PBMC'
          AND sub.response IN ('yes', 'no')
    """
    return pd.read_sql_query(query, conn)


def compute_percentages(wide: pd.DataFrame) -> pd.DataFrame:
    wide["total_count"] = wide[CELL_TYPES].sum(axis=1)
    for pop in CELL_TYPES:
        wide[f"{pop}_pct"] = wide[pop] / wide["total_count"] * 100
    freq_df = wide.melt(
        id_vars=["sample", "subject_id", "response", "sex", "age", "project_id", "time"],
        value_vars=[f"{p}_pct" for p in CELL_TYPES],
        var_name="population",
        value_name="percentage",
    )
    freq_df["population"] = freq_df["population"].str.replace("_pct", "", regex=False)
    return freq_df


def run_stats(freq_df: pd.DataFrame) -> pd.DataFrame:
    # GEE: percentage ~ response * time + sex + age + C(project_id)
    # coef_response  = difference between responders and non-responders at day 0 (baseline)
    # coef_resp:time = how that gap changes per day (trajectory)
    # coef_at_day7   = derived: coef_response + 7 * coef_resp:time (no re-fitting needed)
    # BH FDR across 10 tests (5 populations × 2 key terms)
    rows = []
    for pop in CELL_TYPES:
        pop_df = freq_df[freq_df.population == pop].copy()
        m = GEE.from_formula(
            "percentage ~ response * time + sex + age + C(project_id)",
            groups="subject_id",
            data=pop_df,
            family=Gaussian(),
            cov_struct=Exchangeable(),
        )
        r = m.fit()
        coef_resp = r.params.get("response[T.yes]",      float("nan"))
        coef_traj = r.params.get("response[T.yes]:time", float("nan"))
        rows.append({
            "population":     pop,
            "coef_response":  round(coef_resp, 4),
            "p_response":     round(r.pvalues.get("response[T.yes]",      float("nan")), 4),
            "coef_resp:time": round(coef_traj, 4),
            "p_resp:time":    round(r.pvalues.get("response[T.yes]:time", float("nan")), 4),
            "coef_at_day7":   round(coef_resp + 7 * coef_traj, 4),
        })

    results_df = pd.DataFrame(rows)

    all_p = results_df["p_response"].tolist() + results_df["p_resp:time"].tolist()
    _, all_p_adj, _, _ = multipletests(all_p, method="fdr_bh")
    results_df["p_adj_response"]  = [round(p, 4) for p in all_p_adj[:5]]
    results_df["p_adj_resp:time"] = [round(p, 4) for p in all_p_adj[5:]]
    results_df["sig_response"]    = all_p_adj[:5] < 0.05
    results_df["sig_resp:time"]   = all_p_adj[5:] < 0.05

    return results_df


def compare_responders(conn: sqlite3.Connection):
    wide     = fetch_cohort(conn)
    freq_df  = compute_percentages(wide)
    stats_df = run_stats(freq_df)
    return freq_df, stats_df
