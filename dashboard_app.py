import dash
from dash import dcc, html, dash_table, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import dash_bootstrap_components as dbc
import numpy as np
from analysis import (
    get_connection,
    compute_frequencies,
    compare_responders,
    melanoma_baseline_subset,
)
from analysis.db import CELL_TYPES

conn = get_connection()
freq_df                              = compute_frequencies(conn)
cohort_df, stats_df                  = compare_responders(conn)
by_project, by_response, by_sex, avg_b = melanoma_baseline_subset(conn)
conn.close()

# Summary counts for metric cards
total_subjects   = cohort_df["subject_id"].nunique()
n_responders     = cohort_df[cohort_df["response"] == "yes"]["subject_id"].nunique()
n_non_responders = cohort_df[cohort_df["response"] == "no"]["subject_id"].nunique()
total_samples    = cohort_df["sample"].nunique()
n_projects       = cohort_df["project_id"].nunique()

# Overview: median % by population and response
overview_df = (
    cohort_df
    .groupby(["population", "response"])["percentage"]
    .median()
    .reset_index()
    .rename(columns={"percentage": "median_pct"})
)

# Time trend: mean +/- SEM by population, response, time
trend_df = (
    cohort_df
    .groupby(["population", "response", "time"])["percentage"]
    .agg(["mean", "std", "count"])
    .reset_index()
)
trend_df["sem"] = trend_df["std"] / np.sqrt(trend_df["count"])

# Stats display table
stats_display = stats_df.rename(columns={
    "coef_response":  "Coef (day 0)",
    "p_response":     "p",
    "p_adj_response": "p_adj",
    "sig_response":   "Sig",
    "coef_resp:time": "Coef x time",
    "p_resp:time":    "p (x time)",
    "p_adj_resp:time":"p_adj (x time)",
    "sig_resp:time":  "Sig (x time)",
    "coef_at_day7":   "Coef (day 7)",
}).copy()
stats_display["Sig"]        = stats_display["Sig"].astype(str)
stats_display["Sig (x time)"] = stats_display["Sig (x time)"].astype(str)

# Static figures
overview_fig = px.bar(
    overview_df,
    x="population", y="median_pct", color="response",
    barmode="group",
    color_discrete_map={"yes": "#1f77b4", "no": "#ff7f0e"},
    category_orders={"population": CELL_TYPES, "response": ["no", "yes"]},
    title="Median Cell Population Frequencies by Response (All Time Points)",
    labels={"median_pct": "Median Relative Frequency (%)", "population": "Cell Population", "response": "Response"},
)

box_fig_all = px.box(
    cohort_df,
    x="population", y="percentage", color="response",
    color_discrete_map={"yes": "#1f77b4", "no": "#ff7f0e"},
    category_orders={"population": CELL_TYPES, "response": ["no", "yes"]},
    title="Cell Population Frequencies: Responders vs Non-Responders (All Time Points)",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population", "response": "Response"},
)

box_fig_baseline = px.box(
    cohort_df[cohort_df["time"] == 0],
    x="population", y="percentage", color="response",
    color_discrete_map={"yes": "#1f77b4", "no": "#ff7f0e"},
    category_orders={"population": CELL_TYPES, "response": ["no", "yes"]},
    title="Cell Population Frequencies: Responders vs Non-Responders (Baseline Only, Day 0)",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population", "response": "Response"},
)

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

hist_fig = px.histogram(
    freq_df,
    x="percentage", color="population",
    barmode="overlay", opacity=0.6, histnorm="probability density",
    title="Cell Population Frequency Distribution (All Samples)",
    labels={"percentage": "Relative Frequency (%)", "population": "Cell Population"},
)


def metric_card(label, value, color="primary"):
    return dbc.Card(
        dbc.CardBody([
            html.H3(str(value), className="card-title text-center mb-1"),
            html.P(label, className="card-text text-center text-muted small"),
        ]),
        color=color, outline=True,
    )


app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container([
    html.H2("Clinical Trial Dashboard", className="my-3"),
    html.P("Melanoma patients on miraclib — PBMC samples", className="text-muted mb-4"),

    dbc.Tabs([

        # Tab 1: Overview
        dbc.Tab(label="Overview", children=[
            html.Br(),
            dbc.Row([
                dbc.Col(metric_card("Total Subjects", total_subjects)),
                dbc.Col(metric_card("Responders", n_responders, "success")),
                dbc.Col(metric_card("Non-Responders", n_non_responders, "warning")),
                dbc.Col(metric_card("PBMC Samples", total_samples)),
                dbc.Col(metric_card("Projects", n_projects)),
            ], className="mb-4 g-2"),
            dbc.Alert(
                "No cell population shows a significant difference at baseline between responders "
                "and non-responders (all FDR-adjusted p > 0.05). B cell trajectories show a nominally "
                "significant differential decline in responders (p = 0.016, p_adj = 0.082) that does not "
                "survive correction. CD4 T cells show a notable divergence by day 7 of treatment.",
                color="info",
            ),
            dcc.Graph(figure=overview_fig),
        ]),

        # Tab 2: Cell Population Comparison (Part 3)
        dbc.Tab(label="Cell Population Comparison", children=[
            html.Br(),
            dbc.Row([
                dbc.Col([
                    html.Label("Time points:"),
                    dcc.RadioItems(
                        id="time-toggle",
                        options=[
                            {"label": "  All (day 0, 7, 14)", "value": "all"},
                            {"label": "  Baseline only (day 0)", "value": "baseline"},
                        ],
                        value="all",
                        inline=True,
                        className="mt-1",
                    ),
                ]),
            ], className="mb-2"),
            dcc.Graph(id="box-fig"),
            html.Hr(),
            html.H5("Mean Frequency over Time by Response"),
            dcc.Dropdown(
                id="trend-pop-dropdown",
                options=[{"label": p, "value": p} for p in CELL_TYPES],
                value="b_cell",
                clearable=False,
                style={"width": "300px"},
                className="mb-2",
            ),
            dcc.Graph(id="trend-fig"),
            html.Hr(),
            html.H5("GEE Statistical Results"),
            html.P(
                "Reference: day 0 (baseline). BH FDR across 10 tests (5 populations x 2 terms). "
                "Coef (day 0) = difference at baseline; Coef (day 7) = derived effect at treatment midpoint.",
                className="text-muted",
            ),
            dash_table.DataTable(
                data=stats_display.to_dict("records"),
                columns=[{"name": c, "id": c} for c in stats_display.columns],
                style_table={"overflowX": "auto"},
                style_cell={"textAlign": "center", "fontSize": "13px"},
                style_header={"fontWeight": "bold"},
                style_data_conditional=[
                    {
                        "if": {"filter_query": '{Sig} = "True"'},
                        "backgroundColor": "#d4edda",
                        "color": "black",
                    },
                ],
            ),
        ]),

        # Tab 3: Baseline Subset (Part 4)
        dbc.Tab(label="Baseline Subset", children=[
            html.Br(),
            dbc.Row([
                dbc.Col(
                    metric_card("Avg B Cells — Melanoma Male Responders (Day 0)", f"{avg_b:.2f}"),
                    width=4,
                ),
            ], className="mb-4"),
            dbc.Row([
                dbc.Col(dcc.Graph(figure=proj_fig)),
                dbc.Col(dcc.Graph(figure=resp_fig)),
                dbc.Col(dcc.Graph(figure=sex_fig)),
            ]),
        ]),

        # Tab 4: Data Overview (Part 2)
        dbc.Tab(label="Data Overview", children=[
            html.Br(),
            dcc.Graph(figure=hist_fig),
            html.Hr(),
            dash_table.DataTable(
                data=freq_df.head(200).to_dict("records"),
                columns=[{"name": c, "id": c} for c in freq_df.columns],
                page_size=15,
                style_table={"overflowX": "auto"},
                filter_action="native",
                sort_action="native",
            ),
        ]),

        # Tab 5: Methods
        dbc.Tab(label="Methods", children=[
            html.Br(),
            dbc.Row([
                dbc.Col(dcc.Markdown("""
### Data

656 melanoma patients treated with miraclib, PBMC samples collected at days 0, 7, and 14.
3 projects total (prj1, prj2, prj3). prj2 contributed no PBMC samples and is excluded from PBMC analyses.

### Part 2: Cell Frequency Summary

Relative frequencies computed as each population's raw count divided by the sum across all 5 populations per sample.

### Part 3: Responder vs Non-Responder Comparison

Each subject contributes 3 repeated PBMC samples, violating the independence assumption of standard tests (Mann-Whitney U, t-test). **Generalized Estimating Equations (GEE)** were used with exchangeable working correlation to account for within-subject clustering.

**Model:** `percentage ~ response * time + sex + age + C(project_id)`

| Term | Meaning |
|---|---|
| response | Difference between groups at baseline (day 0) |
| time | Overall time trend across treatment |
| response x time | Do responders show a different trajectory over time? |
| sex, age | Biology-motivated confounders |
| project_id | Batch/cohort effect correction |

**Family:** Gaussian with identity link (values in [2.1%, 49%], skewness 0.19-0.59, no boundary effects)

**Correlation:** Exchangeable (estimated rho close to 0 and results robust across Independence and AR(1))

**Multiple testing:** Benjamini-Hochberg FDR across 10 tests (5 populations x 2 terms)

### Part 4: Baseline Subset

Melanoma + miraclib + PBMC + time=0 filter applied at the SQL level. Subject-level counts deduplicated before grouping by response and sex.

### Key Finding

No cell population differs significantly at baseline between responders and non-responders. CD4 T cells diverge by day 7 (+0.65 pp, derived from interaction term). B cell trajectories show a nominally significant differential decline in responders (p = 0.016) that does not survive FDR correction (p_adj = 0.082).
                """), width=8),
            ]),
        ]),

    ]),
], fluid=True)


@app.callback(Output("box-fig", "figure"), Input("time-toggle", "value"))
def update_boxplot(time_val):
    return box_fig_baseline if time_val == "baseline" else box_fig_all


@app.callback(Output("trend-fig", "figure"), Input("trend-pop-dropdown", "value"))
def update_trend(pop):
    df = trend_df[trend_df["population"] == pop]
    fig = go.Figure()
    for resp, color in [("no", "#ff7f0e"), ("yes", "#1f77b4")]:
        d = df[df["response"] == resp].sort_values("time")
        fig.add_trace(go.Scatter(
            x=d["time"], y=d["mean"],
            error_y=dict(type="data", array=d["sem"].tolist(), visible=True),
            mode="lines+markers",
            name=f"Response: {resp}",
            line=dict(color=color),
        ))
    fig.update_layout(
        title=f"{pop} — Mean Frequency over Time (mean +/- SEM)",
        xaxis=dict(title="Day", tickvals=[0, 7, 14]),
        yaxis_title="Mean Relative Frequency (%)",
    )
    return fig


if __name__ == "__main__":
    app.run(debug=True)
