"""
streamlit_app.py
Air Quality Health Risk Predictor — Streamlit Web App

Run with:
    cd air_quality_portfolio
    streamlit run app/streamlit_app.py
"""

import os
import sys
import joblib
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import date, timedelta

# ── Page Config ──────────────────────────────────────────────
st.set_page_config(
    page_title="AQI Risk Predictor",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Load Model ───────────────────────────────────────────────
@st.cache_resource
def load_model():
    model_path = Path(__file__).parent.parent / "models" / "aqi_risk_model.pkl"
    if not model_path.exists():
        st.error("Model not found. Run `python models/train_model.py` first.")
        st.stop()
    return joblib.load(model_path)

@st.cache_data
def load_history():
    fp = Path(__file__).parent.parent / "data" / "processed" / "features.csv"
    if fp.exists():
        df = pd.read_csv(fp, parse_dates=["full_date"])
        # Ensure category column exists (it may be named 'aqi_category')
        if "aqi_category" not in df.columns and "category" in df.columns:
            df["aqi_category"] = df["category"]
        return df
    return pd.DataFrame()

artifacts = load_model()
model            = artifacts["model"]
FEATURES         = artifacts["features"]
le_state         = artifacts["le_state"]
le_season        = artifacts["le_season"]
le_param         = artifacts["le_param"]
le_state_season  = artifacts.get("le_state_season")  # may be None in older models
STATE_LIST       = sorted(artifacts["state_classes"])
SEASON_LIST      = artifacts["season_classes"]
PARAM_LIST       = artifacts["param_classes"]

# Thresholds (saved in latest training)
best_threshold = artifacts.get("best_threshold", 0.5)            # F2-optimal
thresh_f1      = artifacts.get("threshold_f1", 0.5)              # optional
thresh_prec20  = artifacts.get("threshold_prec20", 0.5)          # optional

df_hist = load_history()

# ── Helpers ───────────────────────────────────────────────────
def get_season(month: int) -> str:
    if month in [3,4,5]:   return "Spring"
    if month in [6,7,8]:   return "Summer"
    if month in [9,10,11]: return "Fall"
    return "Winter"

def encode_safe(le, val):
    """Label-encode with fallback to 0 for unknown labels."""
    try:
        return int(le.transform([val])[0])
    except ValueError:
        return 0

def predict_risk(state, month, day_of_week, is_weekend,
                 current_aqi, lag1, lag2, lag3, lag7, lag14,
                 roll7, roll14, roll30, roll7_std, defining_param):
    today = date.today()
    season   = get_season(month)
    doy      = today.timetuple().tm_yday
    year_val = today.year
    quarter  = (month - 1) // 3 + 1
    week_of_year = today.isocalendar()[1]

    # Encode categoricals
    state_enc = encode_safe(le_state, state)
    season_enc = encode_safe(le_season, season)
    param_enc = encode_safe(le_param, defining_param)

    # State-season interaction
    if le_state_season is not None:
        ss_interaction = f"{state_enc}_{season_enc}"
        state_season_enc = encode_safe(le_state_season, ss_interaction)
    else:
        state_season_enc = 0  # fallback if encoder missing

    # Compute derived features (handle division by zero)
    eps = 1e-5
    aqi_trend_7d   = lag1 - lag7
    aqi_trend_14d  = lag1 - lag14 if lag14 is not None else 0
    aqi_change_1d  = lag1 - lag2
    aqi_change_7d  = lag7 - lag14 if lag14 is not None else 0
    aqi_ratio_7d   = lag1 / (lag7 + eps)
    aqi_ratio_30d  = lag1 / (roll30 + eps)

    # Build feature vector in exact order of FEATURES
    row = {
        "year":             year_val,
        "month":            month,
        "quarter":          quarter,
        "day_of_week":      day_of_week,
        "day_of_year":      doy,
        "is_weekend":       int(is_weekend),
        "season_enc":       season_enc,
        "state_enc":        state_enc,
        "param_enc":        param_enc,
        "month_sin":        np.sin(2 * np.pi * month / 12),
        "month_cos":        np.cos(2 * np.pi * month / 12),
        "dow_sin":          np.sin(2 * np.pi * day_of_week / 7),
        "dow_cos":          np.cos(2 * np.pi * day_of_week / 7),
        "week_sin":         np.sin(2 * np.pi * week_of_year / 52),
        "week_cos":         np.cos(2 * np.pi * week_of_year / 52),
        "state_season_enc": state_season_enc,
        "aqi_lag1":         lag1,
        "aqi_lag2":         lag2,
        "aqi_lag3":         lag3,
        "aqi_lag7":         lag7,
        "aqi_lag14":        lag14 if lag14 is not None else lag7,  # fallback
        "aqi_roll7":        roll7,
        "aqi_roll14":       roll14 if roll14 is not None else roll7,  # fallback
        "aqi_roll30":       roll30,
        "aqi_roll7_std":    roll7_std if roll7_std is not None else 0,
        "aqi_trend_7d":     aqi_trend_7d,
        "aqi_trend_14d":    aqi_trend_14d,
        "aqi_change_1d":    aqi_change_1d,
        "aqi_change_7d":    aqi_change_7d,
        "aqi_ratio_7d":     aqi_ratio_7d,
        "aqi_ratio_30d":    aqi_ratio_30d,
    }

    # Ensure correct column order
    X = pd.DataFrame([row])[FEATURES]
    prob  = model.predict_proba(X)[0][1]
    label = 1 if prob >= best_threshold else 0
    return label, prob, X


# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.image("https://www.epa.gov/sites/default/files/2013-06/epa_seal_verysmall_trim.gif", width=60)
    st.title("🌿 AQI Risk Predictor")
    st.markdown("**Predict tomorrow's air quality health risk** based on current conditions.")
    st.divider()

    state = st.selectbox("📍 State", STATE_LIST, index=STATE_LIST.index("California") if "California" in STATE_LIST else 0)
    today_date = date.today()
    month       = st.slider("📅 Month", 1, 12, today_date.month)
    day_of_week = st.slider("📅 Day of Week (1=Mon, 7=Sun)", 1, 7, today_date.weekday() + 1)
    is_weekend  = day_of_week >= 6
    st.caption(f"Season: **{get_season(month)}** | Weekend: **{'Yes' if is_weekend else 'No'}**")

    st.divider()
    st.subheader("🔬 Recent AQI History")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        lag1  = st.slider("Yesterday (lag 1)", 0, 500, 65)
        lag2  = st.slider("2 days ago (lag 2)", 0, 500, 60)
        lag3  = st.slider("3 days ago (lag 3)", 0, 500, 58)
        lag7  = st.slider("7 days ago (lag 7)", 0, 500, 50)
    with col_s2:
        lag14 = st.slider("14 days ago (lag 14)", 0, 500, 45)
        roll7 = st.number_input("7‑day rolling avg AQI", value=58.0, step=1.0)
        roll14 = st.number_input("14‑day rolling avg AQI", value=54.0, step=1.0)
        roll30 = st.number_input("30‑day rolling avg AQI", value=52.0, step=1.0)
        roll7_std = st.number_input("7‑day rolling std. dev.", value=8.0, step=0.5, min_value=0.0)

    defining_param = st.selectbox("Defining Pollutant", PARAM_LIST)

    st.divider()
    thresh_option = st.radio(
        "⚠️ Alert threshold strategy",
        options=["F2-optimal (recall focus)", "F1-optimal (balanced)", "Precision ≥ 20%"],
        index=0
    )
    st.caption("Higher recall catches more danger days, but more false alerts. Lower recall is more precise.")
    predict_btn = st.button("🔮 Predict Risk", type="primary", use_container_width=True)


# ── Main Page ─────────────────────────────────────────────────
st.title("🌍 Urban Air Quality Health Risk Predictor")
st.markdown(
    "This tool predicts whether tomorrow's air quality in your area will reach a "
    "**health-risk threshold** (Unhealthy for Sensitive Groups or worse) based on recent trends. "
    "Data powered by the US EPA AirData program."
)
st.divider()

# ── Prediction Result ─────────────────────────────────────────
if predict_btn:
    # Choose threshold based on user selection
    threshold_map = {
        "F2-optimal (recall focus)":  best_threshold,
        "F1-optimal (balanced)":      thresh_f1 if thresh_f1 is not None else best_threshold,
        "Precision ≥ 20%":            thresh_prec20 if thresh_prec20 is not None else best_threshold,
    }
    active_threshold = threshold_map[thresh_option]

    label, prob, X_input = predict_risk(
        state, month, day_of_week, is_weekend,
        0, lag1, lag2, lag3, lag7, lag14,
        roll7, roll14, roll30, roll7_std, defining_param
    )
    # Override prediction with active threshold
    label = 1 if prob >= active_threshold else 0

    col1, col2, col3 = st.columns([2,2,2])

    with col1:
        if label == 1:
            st.error(f"### 🚨 AT RISK\nTomorrow's air quality predicted to be **Unhealthy or worse**.\n(threshold = {active_threshold:.3f})")
        else:
            st.success(f"### ✅ SAFE\nTomorrow's air quality predicted to be **Good or Moderate**.\n(threshold = {active_threshold:.3f})")

    with col2:
        gauge_threshold_pct = active_threshold * 100
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=round(prob * 100, 1),
            title={"text": "At-Risk Probability (%)"},
            delta={"reference": gauge_threshold_pct},
            gauge={
                "axis": {"range": [0, 100]},
                "bar":  {"color": "#dc3545" if prob >= active_threshold else "#28a745"},
                "steps": [
                    {"range": [0, 30],  "color": "#d4edda"},
                    {"range": [30, 50], "color": "#fff3cd"},
                    {"range": [50, 100],"color": "#f8d7da"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 3},
                    "thickness": 0.75,
                    "value": gauge_threshold_pct,
                },
            },
        ))
        fig_gauge.update_layout(height=250, margin=dict(t=40,b=10,l=20,r=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col3:
        st.metric("Prediction Confidence", f"{max(prob, 1-prob)*100:.1f}%")
        st.metric("Current AQI (today)", lag1,
                  delta=f"{lag1 - lag7:+.0f} vs 7 days ago")
        category_text = "Unhealthy or worse" if label == 1 else "Good / Moderate"
        st.metric("Predicted Category", category_text)

    st.divider()

    # AQI trend mini-chart
    aqi_vals = [lag14, lag7, lag3, lag2, lag1]
    labels   = ["14d ago","7d ago","3d ago","2d ago","Yesterday"]
    fig_trend = px.line(
        x=labels, y=aqi_vals,
        markers=True,
        title=f"Recent AQI Trend — {state}",
        labels={"x":"","y":"AQI"},
        color_discrete_sequence=["#5C85D6"],
    )
    fig_trend.add_hline(y=100, line_dash="dash", line_color="orange",
                        annotation_text="Moderate threshold")
    fig_trend.add_hline(y=150, line_dash="dash", line_color="red",
                        annotation_text="USG threshold")
    fig_trend.update_layout(height=300)
    st.plotly_chart(fig_trend, use_container_width=True)

    # Health guidance
    if label == 1:
        st.warning("""
        **⚠️ Health Guidance for At-Risk Days:**
        - Sensitive groups (children, elderly, asthma patients): **stay indoors**
        - Avoid strenuous outdoor exercise
        - Keep windows closed; use air purifiers indoors
        - Check real-time AQI at [AirNow.gov](https://www.airnow.gov/)
        """)
    else:
        st.info("""
        **✅ Enjoy the clean air! Tips:**
        - Great day for outdoor activities
        - Continue monitoring trends in high-wildfire or high-traffic seasons
        - Check [AirNow.gov](https://www.airnow.gov/) for real-time readings
        """)

# ── Historical Insights ───────────────────────────────────────
st.subheader("📊 Historical AQI Insights (2022–2025)")

if not df_hist.empty:
    tab1, tab2, tab3 = st.tabs(["State Trends", "Seasonal Patterns", "Raw Data"])

    with tab1:
        selected_states = st.multiselect(
            "Select states to compare:",
            options=sorted(df_hist.state_name.unique()),
            default=["California","Texas","New York"] if all(
                s in df_hist.state_name.unique()
                for s in ["California","Texas","New York"]) else [],
        )
        if selected_states:
            sub = df_hist[df_hist.state_name.isin(selected_states)]
            monthly = sub.groupby(["state_name","year","month"])["aqi_value"].mean().reset_index()
            monthly["date_str"] = pd.to_datetime(monthly[["year","month"]].assign(day=1)).dt.strftime("%Y-%m")
            fig = px.line(monthly, x="date_str", y="aqi_value", color="state_name",
                         title="Monthly Average AQI by State",
                         labels={"aqi_value":"Avg AQI","date_str":"Month","state_name":"State"})
            st.plotly_chart(fig, use_container_width=True)

    with tab2:
        season_data = df_hist.groupby("season")["aqi_value"].agg(["mean","median","std"]).reset_index()
        fig_s = px.bar(season_data, x="season", y="mean", error_y="std",
                    title="Average AQI by Season (National)",
                    color="mean",
                    color_continuous_scale=["green","yellow","orange","red"],
                    labels={"mean":"Avg AQI","season":"Season"})
        st.plotly_chart(fig_s, use_container_width=True)

    with tab3:
        n_rows = st.slider("Rows to show", 50, 500, 100)
        # Build display columns based on what's available
        preferred = ["full_date", "state_name", "county_name", "aqi_value", "aqi_category", "target"]
        display_cols = [col for col in preferred if col in df_hist.columns]
        st.dataframe(
            df_hist[display_cols]
            .sort_values("full_date", ascending=False)
            .head(n_rows)
            .reset_index(drop=True),
            use_container_width=True,
        )
else:
    st.info("Run the full pipeline to see historical charts here.")

st.divider()
st.caption(
    "Data Source: [EPA AirData](https://www.epa.gov/outdoor-air-quality-data) | "
    "Model: XGBoost (trained on 2022–2024, tested on 2025) | "
    "SMOTE applied for class imbalance | "
    "Portfolio project by Sihle Kalolo — May 2026"
)