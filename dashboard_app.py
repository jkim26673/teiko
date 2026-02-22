import dash
from dash import dcc, html, dash_table
import plotly.express as px
import dash_bootstrap_components as dbc
from analysis import (
    get_connection,
    compute_frequencies,
    compare_responders,
    melanoma_baseline_subset,
)

conn = get_connection()
freq_df                              = compute_frequencies(conn)
cohort_df, stats_df                  = compare_responders(conn)
by_project, by_response, by_sex, avg_b = melanoma_baseline_subset(conn)
conn.close()

# Part 2 histogram
hist_fig = px.histogram(
    freq_df,
    x="percentage",
    color="population",
    barmode="overlay",
    opacity=0.6,
    histnorm="probability density",
    title="Cell Population Frequency Distribution (All Samples)",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population"},
)

# Part 3 boxplot
box_fig = px.box(
    cohort_df,
    x="population",
    y="percentage",
    color="response",
    title="Cell Population Frequencies: Responders vs Non-Responders",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population", "response": "Response"},
)

# Part 4 bar charts
proj_fig = px.bar(
    by_project, x="project_id", y="sample_count",
    title="Baseline Samples per Project",
    labels={"project_id": "Project", "sample_count": "Sample Count"},
)
resp_fig = px.bar(
    by_response, x="response", y="subject_count",
    title="Subjects by Response",
    labels={"response": "Response", "subject_count": "Subject Count"},
)
sex_fig = px.bar(
    by_sex, x="sex", y="subject_count",
    title="Subjects by Sex",
    labels={"sex": "Sex", "subject_count": "Subject Count"},
)

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = dbc.Container([
    html.H2("Clinical Trial Dashboard", className="my-3"),

    dbc.Tabs([
        dbc.Tab(label="Part 2: Frequency Overview", children=[
            html.Br(),
            dash_table.DataTable(
                data=freq_df.head(50).to_dict("records"),
                columns=[{"name": c, "id": c} for c in freq_df.columns],
                page_size=15,
                style_table={"overflowX": "auto"},
            ),
            dcc.Graph(figure=hist_fig),
        ]),

        dbc.Tab(label="Part 3: Responder Comparison", children=[
            html.Br(),
            html.P(
                "GEE model: percentage ~ response × time + sex + age + project. "
                "Time centered at day 7 (midpoint). BH FDR across 10 tests (5 populations × 2 terms). "
                "Coef (response) = difference at day 7; Coef (response×time) = change in gap per day.",
                className="text-muted",
            ),
            dash_table.DataTable(
                data=stats_df.rename(columns={
                    "coef_response":  "Coef (response, day 7)",
                    "p_response":     "p (response)",
                    "coef_resp:time": "Coef (response\u00d7time)",
                    "p_resp:time":    "p (response\u00d7time)",
                    "p_adj_response": "p_adj (response)",
                    "p_adj_resp:time":"p_adj (response\u00d7time)",
                    "sig_response":   "Sig (response)",
                    "sig_resp:time":  "Sig (response\u00d7time)",
                }).to_dict("records"),
                columns=[
                    {"name": "Population",               "id": "population"},
                    {"name": "Coef (response, day 7)",   "id": "Coef (response, day 7)"},
                    {"name": "p (response)",             "id": "p (response)"},
                    {"name": "p_adj (response)",         "id": "p_adj (response)"},
                    {"name": "Sig (response)",           "id": "Sig (response)"},
                    {"name": "Coef (response\u00d7time)","id": "Coef (response\u00d7time)"},
                    {"name": "p (response\u00d7time)",   "id": "p (response\u00d7time)"},
                    {"name": "p_adj (response\u00d7time)","id": "p_adj (response\u00d7time)"},
                    {"name": "Sig (response\u00d7time)", "id": "Sig (response\u00d7time)"},
                ],
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "center"},
                style_header={"fontWeight": "bold"},
            ),
            dcc.Graph(figure=box_fig),
        ]),

        dbc.Tab(label="Part 4: Baseline Subset", children=[
            html.Br(),
            html.H5(f"Avg B Cells — Melanoma Male Responders at Baseline: {avg_b:.2f}"),
            html.Br(),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=proj_fig)),
                dbc.Col(dcc.Graph(figure=resp_fig)),
                dbc.Col(dcc.Graph(figure=sex_fig)),
            ]),
        ]),
    ]),
], fluid=True)

if __name__ == "__main__":
    app.run(debug=True)
