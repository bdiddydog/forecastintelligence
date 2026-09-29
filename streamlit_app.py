from __future__ import annotations
import os
from datetime import datetime
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app.config import APP_NAME, APP_TAGLINE, ZONES
from app.services.nws import NWSClient, normalize_observation
from app.services.models import latest_model_status
from app.engine.consensus import confidence_score
from app.data.demo import DEMO

st.set_page_config(page_title=APP_NAME, page_icon="🌦️", layout="wide")

CSS = """
<style>
.block-container {padding-top: 1rem; padding-bottom: 2rem;}
[data-testid='stMetricValue'] {font-size: 1.6rem;}
.dwg-title {font-size:2rem;font-weight:800;letter-spacing:.02em}
.dwg-sub {opacity:.75;margin-top:-8px;margin-bottom:14px}
.card {border:1px solid rgba(120,160,220,.25); border-radius:12px; padding:12px; background:rgba(20,35,55,.22)}
.status-good {color:#31d07c;font-weight:700}
.status-warn {color:#f2c14e;font-weight:700}
.small {font-size:.85rem; opacity:.8}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.markdown(f"<div class='dwg-title'>🌦️ {APP_NAME}</div>", unsafe_allow_html=True)
st.markdown(f"<div class='dwg-sub'>{APP_TAGLINE} • v0.1</div>", unsafe_allow_html=True)

with st.sidebar:
    st.header("DWG Command Center")
    page = st.radio("Workspace", ["Dashboard", "Observations", "Model Status", "Forecast Desk", "Verification"])
    live = st.toggle("Use live NWS data", value=True)
    st.caption("If the NWS feed cannot be reached, the app automatically falls back to demo data.")

@st.cache_data(ttl=300, show_spinner=False)
def get_obs(lat, lon):
    client = NWSClient()
    return normalize_observation(client.latest_observation(lat, lon))

@st.cache_data(ttl=120, show_spinner=False)
def get_alerts():
    return NWSClient().alerts_for_area("DE")

@st.cache_data(ttl=900, show_spinner=False)
def get_model_status():
    return latest_model_status()


def observation_for(zone):
    if live:
        try:
            return get_obs(zone.lat, zone.lon), True
        except Exception:
            pass
    return DEMO[zone.city], False

if page == "Dashboard":
    a,b,c = st.columns([1.5,1,1])
    with a:
        st.subheader("Operational Overview")
    with b:
        st.metric("Local time", datetime.now().strftime("%I:%M %p"))
    with c:
        st.metric("System", "LIVE" if live else "DEMO")

    try:
        alerts = get_alerts() if live else {"features": []}
        alert_features = alerts.get("features", [])
    except Exception:
        alert_features = []

    if alert_features:
        st.warning(f"{len(alert_features)} active NWS alert(s) for Delaware")
        with st.expander("View active alerts"):
            for feature in alert_features[:10]:
                p = feature.get("properties", {})
                st.markdown(f"**{p.get('event','Alert')}** — {p.get('headline','')}")
    else:
        st.success("No active Delaware NWS alerts returned by the feed.")

    st.subheader("Delaware Zones")
    cols = st.columns(4)
    rows = []
    for col, zone in zip(cols, ZONES):
        obs, is_live = observation_for(zone)
        rows.append({"zone": zone.name, **obs})
        with col:
            st.markdown(f"### {zone.name}")
            st.caption(f"{zone.city} • {'LIVE' if is_live else 'DEMO'}")
            temp = obs.get("temperature_f")
            st.metric("Temperature", "—" if temp is None else f"{temp:.0f}°F")
            st.write(obs.get("text", ""))
            c1,c2 = st.columns(2)
            c1.metric("Dewpoint", "—" if obs.get("dewpoint_f") is None else f"{obs['dewpoint_f']:.0f}°")
            c2.metric("Gust", "—" if obs.get("gust_mph") is None else f"{obs['gust_mph']:.0f} mph")

    st.subheader("Confidence Engine")
    conf = confidence_score(.78, .72, .70, .74)
    g1,g2 = st.columns([1,3])
    g1.metric("Current system confidence", f"{conf['score']}/100", conf['label'])
    fig = go.Figure(go.Bar(x=list(conf['components'].values()), y=[k.replace('_',' ').title() for k in conf['components']], orientation='h'))
    fig.update_layout(height=260, margin=dict(l=10,r=10,t=10,b=10), xaxis_range=[0,1])
    g2.plotly_chart(fig, use_container_width=True)

    st.subheader("Next Build Layer")
    st.info("v0.1 establishes the live observation/alert foundation and model-run discovery. Point-extracted HRRR/RAP/GFS/GEFS fields plug into the existing Forecast Desk next.")

elif page == "Observations":
    st.header("Live Delaware Observations")
    records = []
    for zone in ZONES:
        obs, is_live = observation_for(zone)
        records.append({
            "Zone": zone.name,
            "Representative": zone.city,
            "Status": "LIVE" if is_live else "DEMO",
            "Temp °F": obs.get("temperature_f"),
            "Dewpoint °F": obs.get("dewpoint_f"),
            "Wind mph": obs.get("wind_mph"),
            "Gust mph": obs.get("gust_mph"),
            "Pressure mb": obs.get("pressure_mb"),
            "Weather": obs.get("text"),
        })
    st.dataframe(pd.DataFrame(records), use_container_width=True, hide_index=True)

elif page == "Model Status":
    st.header("Latest Model Run Status")
    st.caption("Herbie checks multiple NOAA/cloud archives for discoverable GRIB2 files.")
    rows = get_model_status()
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.info("A model shown as discoverable means the requested F00 GRIB file was located. v0.2 will validate all required forecast hours and variables before marking a cycle fully analysis-ready.")

elif page == "Forecast Desk":
    st.header("Brandon's Forecast Desk")
    zone = st.selectbox("Forecast zone", [z.name for z in ZONES])
    st.markdown("#### Automated Guidance")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("QPF consensus", "—")
    c2.metric("Peak gust", "—")
    c3.metric("PoP", "—")
    c4.metric("Confidence", "Framework ready")
    st.caption("Model point extraction is the next data connector; the adjustment and archive workflow is already laid out below.")

    st.markdown("#### Forecaster Adjustment")
    accept = st.radio("Decision", ["Accept automated guidance", "Adjust forecast"], horizontal=True)
    qpf = st.text_input("Adjusted QPF range", placeholder="e.g. 0.75–1.10 in")
    gust = st.text_input("Adjusted peak gust", placeholder="e.g. 35 mph")
    reasons = st.multiselect("Reason for adjustment", ["Model bias", "Observation trend", "Radar evolution", "Synoptic reasoning", "Local climatology", "Other"])
    take = st.text_area("Brandon's Take", placeholder="Your operational interpretation...")
    if st.button("Save forecast decision", type="primary"):
        os.makedirs("data", exist_ok=True)
        path = "data/forecaster_decisions.csv"
        row = pd.DataFrame([{
            "saved_at": datetime.now().isoformat(), "zone": zone, "decision": accept,
            "qpf": qpf, "gust": gust, "reasons": "; ".join(reasons), "brandons_take": take
        }])
        row.to_csv(path, mode="a", header=not os.path.exists(path), index=False)
        st.success(f"Forecast decision saved to {path}")

elif page == "Verification":
    st.header("Verification")
    st.write("This screen will compare issued forecasts with observed outcomes and calculate MAE, bias, timing error, and model performance by Delaware zone.")
    path = "data/forecaster_decisions.csv"
    if os.path.exists(path):
        st.dataframe(pd.read_csv(path), use_container_width=True, hide_index=True)
    else:
        st.info("No saved forecast decisions yet.")
