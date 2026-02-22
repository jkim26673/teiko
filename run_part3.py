import plotly.express as px
from analysis import get_connection, compare_responders

conn = get_connection()
freq_df, stats_df = compare_responders(conn)
conn.close()

# Part 2 summary table for the filtered cohort
summary = freq_df.groupby(["population", "response"])["percentage"].agg(["mean", "median", "std"]).round(2)
summary.columns = ["Mean", "Median", "Std"]
summary.index.names = ["Population", "Response"]
print(summary.to_string())
print()

fig = px.box(
    freq_df,
    x="population",
    y="percentage",
    color="response",
    title="Cell Population Frequencies: Responders vs Non-Responders",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population", "response": "Response"},
)
fig.show()

print(stats_df.to_string(index=False))
