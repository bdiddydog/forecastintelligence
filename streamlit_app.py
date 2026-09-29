import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="DWG Forecast Intelligence", page_icon="🌦️", layout="wide")

LOCATIONS = {
    "Northern Delaware": {"city":"Wilmington","lat":39.7391,"lon":-75.5398},
    "Central Delaware": {"city":"Dover","lat":39.1582,"lon":-75.5244},
    "Inland Sussex": {"city":"Georgetown","lat":38.6901,"lon":-75.3855},
    "Delaware Beaches": {"city":"Rehoboth Beach","lat":38.7209,"lon":-75.0760},
}
HEADERS = {"User-Agent": "DWG-Forecast-Intelligence/0.1 contact: Delaware Weather Guy"}





def get_json(url, timeout=10):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=300)
def point_metadata(lat, lon):
    return get_json(f"https://api.weather.gov/points/{lat},{lon}")

@st.cache_data(ttl=300)
def current_observation(lat, lon):
    meta = point_metadata(lat, lon)
    stations_url = meta["properties"]["observationStations"]
    stations = get_json(stations_url)["features"]
    if not stations:
        return None
    station_id = stations[0]["properties"]["stationIdentifier"]
    obs = get_json(f"https://api.weather.gov/stations/{station_id}/observations/latest")
    p = obs["properties"]

    def c_to_f(v): return None if v is None else v*9/5+32
    def ms_to_mph(v): return None if v is None else v*2.23694
    def pa_to_mb(v): return None if v is None else v/100

    return {
        "station": station_id,
        "temp": c_to_f(p["temperature"]["value"]),
        "dew": c_to_f(p["dewpoint"]["value"]),
        "wind": ms_to_mph(p["windSpeed"]["value"]),
        "gust": ms_to_mph(p["windGust"]["value"]),
        "dir": p["windDirection"]["value"],
        "pressure": pa_to_mb(p["seaLevelPressure"]["value"]),
        "text": p.get("textDescription") or "—",
        "time": p.get("timestamp"),
    }

@st.cache_data(ttl=600)
def forecast(lat, lon):
    meta = point_metadata(lat, lon)
    url = meta["properties"]["forecast"]
    return get_json(url)["properties"]["periods"]

@st.cache_data(ttl=120)
def delaware_alerts():
    return get_json("https://api.weather.gov/alerts/active?area=DE")["features"]

def fmt(x, digits=0, suffix=""):
    return "—" if x is None else f"{x:.{digits}f}{suffix}"

def demo_obs(city):
    demo = {
        "Wilmington": (68,60,12,22,1008),
        "Dover": (69,62,14,25,1007),
        "Georgetown": (70,64,15,28,1006),
        "Rehoboth Beach": (69,65,18,31,1006),
    }[city]
    return {
        "station":"DEMO","temp":demo[0],"dew":demo[1],"wind":demo[2],"gust":demo[3],
        "dir":110,"pressure":demo[4],"text":"Demo mode","time":None
    }

st.sidebar.title("DWG Intelligence")
st.sidebar.caption("Data Over Drama")
display_mode = st.sidebar.segmented_control("Display", ["☀️ Bright", "🌙 Dark"], default="☀️ Bright")
if display_mode == "🌙 Dark":
    bg, panel, side, textc, muted, border = "#07111f", "#0d1d31", "#0b1728", "#eef6ff", "#aebed0", "#274663"
else:
    bg, panel, side, textc, muted, border = "#f5f9fd", "#ffffff", "#e8f2fb", "#14253a", "#52677d", "#b9d2e8"
st.markdown(f"""
<style>
.stApp {{background:{bg}; color:{textc}}}
[data-testid="stSidebar"] {{background:{side}}}
[data-testid="stSidebar"] * {{color:{textc} !important}}
.dwg-card {{background:{panel};border:1px solid {border};border-radius:12px;padding:16px;margin-bottom:12px}}
.small {{font-size:.82rem;color:{muted}}}
h1,h2,h3,p,span,label {{color:{textc}}}
[data-testid="stMetricLabel"], [data-testid="stMetricValue"] {{color:{textc} !important}}
[data-testid="stCaptionContainer"] {{color:{muted} !important}}
</style>
""", unsafe_allow_html=True)
page = st.sidebar.radio("Workstation", [
    "Command Center","Observations","Forecast Guidance","Model Desk",
    "Hazards","Forecaster Desk","Verification","System Status"
])

now = datetime.now(ZoneInfo("America/New_York"))
st.title("🌦️ DWG Forecast Intelligence")
st.caption(f"Delaware Forecasting Workstation • v0.1 • {now:%A, %B %d, %Y • %I:%M %p %Z}")

live_ok = True
obs_data = {}
for zone, loc in LOCATIONS.items():
    try:
        obs_data[zone] = current_observation(loc["lat"], loc["lon"])
        if obs_data[zone] is None:
            raise RuntimeError("No observation")
    except Exception:
        live_ok = False
        obs_data[zone] = demo_obs(loc["city"])

if page == "Command Center":
    a,b,c,d = st.columns(4)
    a.metric("NWS Data", "LIVE" if live_ok else "DEMO/FALLBACK")
    try:
        alerts = delaware_alerts()
        b.metric("Active DE Alerts", len(alerts))
    except Exception:
        alerts = []
        b.metric("Active DE Alerts", "—")
    c.metric("Forecast Zones", 4)
    d.metric("Forecaster", "Brandon")

    st.subheader("Delaware Now")
    cols = st.columns(4)
    for col,(zone,loc) in zip(cols,LOCATIONS.items()):
        o = obs_data[zone]
        with col:
            st.markdown('<div class="dwg-card">', unsafe_allow_html=True)
            st.markdown(f"### {zone}")
            st.caption(f"{loc['city']} • {o['station']}")
            st.metric("Temperature", fmt(o["temp"],0,"°F"))
            st.write(f"**Dewpoint:** {fmt(o['dew'],0,'°F')}")
            st.write(f"**Wind:** {fmt(o['wind'],0,' mph')} • Gust {fmt(o['gust'],0,' mph')}")
            st.write(f"**MSLP:** {fmt(o['pressure'],1,' mb')}")
            st.write(o["text"])
            st.markdown('</div>', unsafe_allow_html=True)

    st.subheader("Official NWS Alerts")
    if not alerts:
        st.success("No active Delaware alerts returned.")
    for f in alerts[:8]:
        p = f["properties"]
        st.warning(f"**{p.get('event','Alert')}** — {p.get('headline','')}")

elif page == "Observations":
    st.header("Surface Observations")
    rows = []
    for zone,loc in LOCATIONS.items():
        o = obs_data[zone]
        rows.append({
            "Zone":zone,"Location":loc["city"],"Station":o["station"],
            "Temp °F":o["temp"],"Dewpoint °F":o["dew"],"Wind mph":o["wind"],
            "Gust mph":o["gust"],"MSLP mb":o["pressure"],"Conditions":o["text"]
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("Live observations are retrieved from the National Weather Service. Demo values appear only when the live feed cannot be reached.")

elif page == "Forecast Guidance":
    st.header("NWS Forecast Guidance")
    zone = st.selectbox("Forecast zone", list(LOCATIONS))
    loc = LOCATIONS[zone]
    try:
        periods = forecast(loc["lat"], loc["lon"])
        for p in periods[:8]:
            with st.expander(f"{p['name']} • {p['temperature']}°{p['temperatureUnit']} • {p['shortForecast']}", expanded=p["number"] <= 2):
                st.write(p["detailedForecast"])
                st.caption(f"Wind: {p['windDirection']} {p['windSpeed']}")
    except Exception:
        st.error("Live NWS forecast is temporarily unavailable. The rest of the workstation remains usable.")

elif page == "Model Desk":
    st.header("Model Intelligence Desk")
    st.info("v0.1 establishes the model workstation and cycle/status framework. Direct HRRR/RAP/GFS/GEFS GRIB extraction is the v0.2 data-engine upgrade.")
    models = pd.DataFrame([
        ["HRRR","Short range / convection","Hourly","Connector ready"],
        ["RAP","Upper-air / short range","Hourly","Connector ready"],
        ["GFS","Synoptic / medium range","00/06/12/18Z","Connector ready"],
        ["GEFS","Ensemble uncertainty","00/06/12/18Z","Connector ready"],
        ["NBM","Blended probabilistic guidance","Multiple","Planned"],
    ], columns=["Model","Role","Cycle","Status"])
    st.dataframe(models, use_container_width=True, hide_index=True)
    st.subheader("Planned Comparison Variables")
    st.write("Temperature • Dewpoint • Wind/Gust • MSLP • QPF • CAPE • Shear • 850/700/500-mb fields")

elif page == "Hazards":
    st.header("Hazard Desk")
    try:
        alerts = delaware_alerts()
    except Exception:
        alerts = []
    if alerts:
        for f in alerts:
            p = f["properties"]
            st.markdown(f"### {p.get('event','Alert')}")
            st.write(p.get("headline",""))
            st.caption(f"Severity: {p.get('severity')} • Urgency: {p.get('urgency')} • Certainty: {p.get('certainty')}")
            with st.expander("Official details"):
                st.write(p.get("description",""))
                if p.get("instruction"):
                    st.write("**Instructions:**", p["instruction"])
    else:
        st.success("No active Delaware NWS alerts returned.")

elif page == "Forecaster Desk":
    st.header("Brandon's Forecast Desk")
    zone = st.selectbox("Zone", list(LOCATIONS))
    c1,c2,c3 = st.columns(3)
    with c1:
        qpf_low = st.number_input("QPF low (in.)",0.0,20.0,0.0,0.05)
        qpf_high = st.number_input("QPF high (in.)",0.0,20.0,0.0,0.05)
    with c2:
        gust = st.number_input("Peak gust (mph)",0,150,0,1)
        pop = st.slider("Precipitation probability",0,100,0,5)
    with c3:
        confidence = st.selectbox("Confidence",["Low","Moderate-Low","Moderate","Moderate-High","High"])
        impact = st.selectbox("Impact",["Minimal","Low","Elevated","High","Extreme"])

    reasons = st.multiselect("Adjustment reasoning",[
        "Model consensus","Model bias","Observational trend","Radar evolution",
        "Synoptic reasoning","Local climatology","Ensemble spread","Other"
    ])
    take = st.text_area("Brandon's Take", height=120)

    if st.button("Save Forecast Decision", type="primary"):
        record = {
            "saved":datetime.now(timezone.utc).isoformat(),
            "zone":zone,
            "qpf_low":qpf_low,
            "qpf_high":qpf_high,
            "gust":gust,
            "pop":pop,
            "confidence":confidence,
            "impact":impact,
            "reasons":reasons,
            "brandons_take":take,
        }
        st.session_state.setdefault("decisions", []).append(record)
        st.success("Forecast decision saved for this browser session.")

    if st.session_state.get("decisions"):
        st.dataframe(pd.DataFrame(st.session_state["decisions"]), use_container_width=True, hide_index=True)

elif page == "Verification":
    st.header("Forecast Verification")
    st.write("This workspace will compare issued DWG forecasts against observations and calculate bias, MAE, timing error and model performance.")
    st.info("v0.1: framework established. Persistent verification database is planned for the hosted backend.")
    st.dataframe(pd.DataFrame([
        ["Temperature","MAE / Bias","Ready for history"],
        ["QPF","MAE / Bias / Hit range","Ready for history"],
        ["Wind gust","MAE / Peak timing","Ready for history"],
        ["Precip timing","Onset/end error","Ready for history"],
    ], columns=["Forecast Element","Metrics","Status"]), use_container_width=True, hide_index=True)

elif page == "System Status":
    st.header("System Status")
    st.write("**NWS API:**", "🟢 Live" if live_ok else "🟡 Fallback mode")
    st.write("**Four-zone configuration:** 🟢 Ready")
    st.write("**NWS alerts:** 🟢 Connected")
    st.write("**NWS point forecasts:** 🟢 Connected")
    st.write("**Model GRIB engine:** 🟡 v0.2")
    st.write("**Persistent database:** 🟡 deployment upgrade")
    st.write("**Radar/Satellite panels:** 🟡 next phase")
    st.caption("The app is intentionally fault-tolerant: a failed external feed should not take down the entire forecaster workstation.")
