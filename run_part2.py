import plotly.express as px
from analysis import get_connection, compute_frequencies

conn = get_connection()
freq = compute_frequencies(conn)
conn.close()

print(f"Rows: {len(freq)}")
print(freq.head(10).to_string(index=False))

fig = px.histogram(
    freq,
    x="percentage",
    color="population",
    barmode="overlay",
    opacity=0.6,
    histnorm="probability density",
    title="Cell Population Frequency Distribution (All Samples)",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population"},
)
fig.show()
