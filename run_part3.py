# Part 3: Responder vs non-responder comparison.
# Cohort: melanoma patients on miraclib, PBMC samples only.
# GEE with exchangeable correlation, time centered at day 7.
# BH FDR across 10 tests (5 populations × 2 terms).

import plotly.express as px
from analysis import get_connection, compare_responders
from analysis.db import CELL_TYPES

conn = get_connection()
freq_df, stats_df = compare_responders(conn)
conn.close()

# Descriptive summary: mean/median/std by population and response
print("Descriptive summary (all time points pooled):")
summary = (
    freq_df
    .groupby(["population", "response"])["percentage"]
    .agg(["mean", "median", "std"])
    .round(2)
)
summary.columns = ["Mean (%)", "Median (%)", "Std"]
summary.index.names = ["Population", "Response"]
print(summary.to_string())
print()

# GEE results table
print("GEE results (BH FDR across 10 tests):")
print(stats_df.to_string(index=False))
print()

# Conclusion
print("--- Conclusion (baseline, day 0) ---")
sig_response = stats_df[stats_df["sig_response"] == True]["population"].tolist()
sig_traj     = stats_df[stats_df["sig_resp:time"] == True]["population"].tolist()

if sig_response:
    for pop in sig_response:
        row = stats_df[stats_df["population"] == pop].iloc[0]
        print(f"  {pop}: significant baseline difference "
              f"(coef={row['coef_response']:+.3f}, p_adj={row['p_adj_response']:.3f})")
else:
    print("  No population shows a significant difference at baseline (day 0) after FDR correction.")

if sig_traj:
    for pop in sig_traj:
        row = stats_df[stats_df["population"] == pop].iloc[0]
        print(f"  {pop}: significant trajectory difference "
              f"(coef={row['coef_resp:time']:+.3f}/day, p_adj={row['p_adj_resp:time']:.3f})")
else:
    print("  No population shows a significant differential trajectory after FDR correction.")

print()
print("--- Interesting finding: effect at day 7 (derived: coef_response + 7 × coef_resp:time) ---")
for _, row in stats_df.iterrows():
    day7 = row["coef_at_day7"]
    direction = "higher" if day7 > 0 else "lower"
    print(f"  {row['population']:>12}  coef at day 7 = {day7:+.3f}  "
          f"(responders {direction} than non-responders at treatment midpoint)")

# Boxplot: all time points pooled, split by response
fig = px.box(
    freq_df,
    x="population",
    y="percentage",
    color="response",
    color_discrete_map={"yes": "#1f77b4", "no": "#ff7f0e"},
    category_orders={"population": CELL_TYPES, "response": ["no", "yes"]},
    title="Relative Frequency of Immune Cell Populations: Responders vs Non-Responders<br>"
          "<sup>All time points pooled (day 0, 7, 14) — melanoma patients on miraclib, PBMC only</sup>",
    labels={
        "percentage":  "Relative Frequency (%)",
        "population":  "Cell Population",
        "response":    "Response",
    },
)
fig.update_layout(
    legend_title_text="Response Status",
    boxgap=0.3,
)
fig.show()
