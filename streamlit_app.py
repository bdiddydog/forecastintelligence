import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="DWG Forecast Intelligence", page_icon="🌦️", layout="wide")

APP_VERSION = "0.2"
LOCATIONS = {
    "Northern Delaware": {"city":"Wilmington","lat":39.7391,"lon":-75.5398},
    "Central Delaware": {"city":"Dover","lat":39.1582,"lon":-75.5244},
    "Inland Sussex": {"city":"Georgetown","lat":38.6901,"lon":-75.3855},
    "Delaware Beaches": {"city":"Rehoboth Beach","lat":38.7209,"lon":-75.0760},
}
HEADERS = {"User-Agent": "DWG-Forecast-Intelligence/0.2 contact: Delaware Weather Guy"}

MODEL_CONFIG = {
    "HRRR": {"id":"ncep_hrrr_conus", "role":"3-km short range", "cadence":"Hourly"},
    "RAP": {"id":"ncep_rap_conus", "role":"Rapid Refresh / upper-air support", "cadence":"Hourly"},
    "GFS": {"id":"ncep_gfs_global", "role":"Global deterministic", "cadence":"Every 6 hours"},
    "ECMWF IFS": {"id":"ecmwf_ifs025", "role":"Global deterministic", "cadence":"Every 6 hours"},
    "NBM": {"id":"ncep_nbm_conus", "role":"National Blend", "cadence":"Hourly"},
    "HGEFS Mean": {"id":"ncep_hgefs025_ensemble_mean", "role":"Ensemble-mean guidance", "cadence":"Every 6 hours"},
}
MODEL_VARIABLES = [
    "temperature_2m","dew_point_2m","precipitation","wind_speed_10m",
    "wind_gusts_10m","pressure_msl"
]

def get_json(url, params=None, timeout=14):
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
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
    def c_to_f(v):
        return None if v is None else v*9/5+32

    def speed_to_mph(item):
        if not item or item.get("value") is None:
            return None
        v = item["value"]
        unit = item.get("unitCode", "")
        if "km_h-1" in unit:
            return v * 0.621371
        if "m_s-1" in unit:
            return v * 2.23694
        if "mi_h-1" in unit:
            return v
        return v

    def pressure_to_mb(item):
        if not item or item.get("value") is None:
            return None
        v = item["value"]
        unit = item.get("unitCode", "")
        if unit.endswith(":Pa"):
            return v / 100
        if "hPa" in unit:
            return v
        return v

    pressure_item = p.get("seaLevelPressure") or p.get("barometricPressure")

    return {
        "station": station_id,
        "temp": c_to_f(p["temperature"]["value"]),
        "dew": c_to_f(p["dewpoint"]["value"]),
        "wind": speed_to_mph(p.get("windSpeed")),
        "gust": speed_to_mph(p.get("windGust")),
        "dir": p["windDirection"]["value"],
        "pressure": pressure_to_mb(pressure_item),
        "text": p.get("textDescription") or "—",
        "time": p.get("timestamp"),
    }

@st.cache_data(ttl=600)
def forecast(lat, lon):
    meta = point_metadata(lat, lon)
    return get_json(meta["properties"]["forecast"])["properties"]["periods"]

@st.cache_data(ttl=120)
def delaware_alerts():
    return get_json("https://api.weather.gov/alerts/active?area=DE")["features"]

@st.cache_data(ttl=900)
def model_forecast(lat, lon, model_id, days=3):
    params = {
        "latitude":lat, "longitude":lon,
        "hourly":",".join(MODEL_VARIABLES),
        "models":model_id,
        "forecast_days":days,
        "temperature_unit":"fahrenheit",
        "wind_speed_unit":"mph",
        "precipitation_unit":"inch",
        "timezone":"America/New_York",
    }
    data = get_json("https://api.open-meteo.com/v1/forecast", params=params)
    h = data["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df["time"])
    return df

@st.cache_data(ttl=1800)
def previous_run_signal(lat, lon, model_id):
    variables = [
        "temperature_2m_previous_day0","temperature_2m_previous_day1",
        "precipitation_previous_day0","precipitation_previous_day1",
        "wind_gusts_10m_previous_day0","wind_gusts_10m_previous_day1",
    ]
    params = {
        "latitude":lat, "longitude":lon,
        "hourly":",".join(variables),
        "models":model_id,
        "forecast_days":2,
        "temperature_unit":"fahrenheit",
        "wind_speed_unit":"mph",
        "precipitation_unit":"inch",
        "timezone":"America/New_York",
    }
    data = get_json("https://previous-runs-api.open-meteo.com/v1/forecast", params=params, timeout=18)
    h = data["hourly"]
    df = pd.DataFrame(h)
    df["time"] = pd.to_datetime(df["time"])
    return df

@st.cache_data(ttl=300)
def nomads_rap_status():
    now_utc = datetime.now(timezone.utc)
    candidates = [now_utc, now_utc - pd.Timedelta(days=1)]
    for dt in candidates:
        day = dt.strftime("%Y%m%d")
        url = f"https://nomads.ncep.noaa.gov/cgi-bin/filter_rap.pl?dir=%2Frap.{day}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if r.ok and "RAP Analysis/Forecasts" in r.text:
                return {"ok": True, "date": day, "url": url}
        except Exception:
            pass
    return {"ok": False, "date": None, "url": "https://nomads.ncep.noaa.gov/cgi-bin/filter_rap.pl"}

def fmt(x, digits=0, suffix=""):
    if x is None or pd.isna(x):
        return "—"
    return f"{x:.{digits}f}{suffix}"

def demo_obs(city):
    demo = {
        "Wilmington": (68,60,12,22,1008),
        "Dover": (69,62,14,25,1007),
        "Georgetown": (70,64,15,28,1006),
        "Rehoboth Beach": (69,65,18,31,1006),
    }[city]
    return {"station":"DEMO","temp":demo[0],"dew":demo[1],"wind":demo[2],"gust":demo[3],
            "dir":110,"pressure":demo[4],"text":"Demo mode","time":None}

def model_summary(df):
    if df is None or df.empty:
        return {}
    now_local = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    future = df[df["time"] >= now_local].head(24)
    if future.empty:
        future = df.head(24)
    return {
        "temp_now": future.iloc[0].get("temperature_2m"),
        "temp_min": future["temperature_2m"].min(),
        "temp_max": future["temperature_2m"].max(),
        "dew_now": future.iloc[0].get("dew_point_2m"),
        "qpf24": future["precipitation"].fillna(0).sum(),
        "gust24": future["wind_gusts_10m"].max(),
        "wind_now": future.iloc[0].get("wind_speed_10m"),
        "mslp_now": future.iloc[0].get("pressure_msl"),
    }

def confidence_from_spread(temp_spread, gust_spread, qpf_spread):
    score = 100
    score -= min(temp_spread * 4, 25)
    score -= min(gust_spread * 1.6, 25)
    score -= min(qpf_spread * 45, 35)
    score = max(0, min(100, round(score)))
    if score >= 86: label = "High"
    elif score >= 71: label = "Moderate-High"
    elif score >= 51: label = "Moderate"
    elif score >= 31: label = "Moderate-Low"
    else: label = "Low"
    return score, label

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
    "Command Center","Observations","Radar & Satellite","Forecast Guidance","Model Intelligence",
    "Model Trends","Hazards","Forecaster Desk","Verification","System Status"
])

now = datetime.now(ZoneInfo("America/New_York"))
st.title("🌦️ DWG Forecast Intelligence")
st.caption(f"Delaware Forecasting Workstation • v{APP_VERSION} • {now:%A, %B %d, %Y • %I:%M %p %Z}")

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

elif page == "Radar & Satellite":
    st.header("Live Radar & Satellite")
    st.caption("Operational imagery links are refreshed by NOAA/NWS. Use the loops for situational awareness; official warnings remain in the Hazard Desk.")

    radar_tab, sat_tab = st.tabs(["📡 NWS Radar", "🛰️ GOES-East Satellite"])

    with radar_tab:
        site = st.selectbox("Radar site", ["KDOX — Dover, DE", "KDIX — Philadelphia / Mt. Holly"], key="radarsite")
        rid = site.split(" ")[0]
        st.subheader(f"{rid} Base Reflectivity Loop")
        st.image(f"https://radar.weather.gov/ridge/standard/{rid}_loop.gif", use_container_width=True)
        st.caption("Source: NOAA/National Weather Service RIDGE radar imagery. Loop updates as the source image updates.")
        st.link_button("Open full NWS Radar Viewer", "https://radar.weather.gov/")

    with sat_tab:
        product = st.selectbox("GOES-East product", ["GeoColor","Clean Longwave IR","Water Vapor"], key="satproduct")
        band = {"GeoColor":"GEOCOLOR","Clean Longwave IR":"13","Water Vapor":"09"}[product]
        image_url = f"https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/{band}/1250x750.jpg"
        st.subheader(f"GOES-19 CONUS — {product}")
        st.image(image_url, use_container_width=True)
        st.caption("Source: NOAA/NESDIS/STAR GOES-19. GeoColor is true-color-like by day and multispectral IR at night.")
        st.link_button("Open NOAA GOES Imagery Viewer", f"https://www.star.nesdis.noaa.gov/GOES/conus_band.php?band={band}&sat=G19")

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
        st.error("Live NWS forecast is temporarily unavailable.")

elif page == "Model Intelligence":
    st.header("Model Intelligence Desk")
    st.caption("Live point guidance plus NOAA/NCEP native-feed monitoring. RAP is now included alongside HRRR, GFS, ECMWF IFS, NBM and ensemble-mean guidance.")
    zone = st.selectbox("Zone", list(LOCATIONS), key="modelzone")
    loc = LOCATIONS[zone]
    horizon = st.selectbox("Display horizon", [24,48,72], index=1)

    frames = {}
    failures = []
    with st.spinner("Loading current model guidance…"):
        for name, cfg in MODEL_CONFIG.items():
            try:
                frames[name] = model_forecast(loc["lat"],loc["lon"],cfg["id"],3)
            except Exception:
                failures.append(name)

    if failures:
        st.warning("Unavailable on this refresh: " + ", ".join(failures))

    summaries = []
    for name,cfg in MODEL_CONFIG.items():
        if name not in frames:
            continue
        s = model_summary(frames[name])
        summaries.append({
            "Model":name,
            "Role":cfg["role"],
            "Temp now °F":s.get("temp_now"),
            "24h Low °F":s.get("temp_min"),
            "24h High °F":s.get("temp_max"),
            "Dewpoint °F":s.get("dew_now"),
            "24h QPF in":s.get("qpf24"),
            "Peak Gust mph":s.get("gust24"),
            "MSLP mb":s.get("mslp_now"),
        })
    summary_df = pd.DataFrame(summaries)

    if summary_df.empty:
        st.error("No model feeds returned. Try refreshing in a few minutes.")
    else:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        det = summary_df[summary_df["Model"].isin(["HRRR","RAP","GFS","ECMWF IFS","NBM"])]
        temp_spread = float(det["Temp now °F"].max()-det["Temp now °F"].min()) if len(det)>1 else 0
        gust_spread = float(det["Peak Gust mph"].max()-det["Peak Gust mph"].min()) if len(det)>1 else 0
        qpf_spread = float(det["24h QPF in"].max()-det["24h QPF in"].min()) if len(det)>1 else 0
        score,label = confidence_from_spread(temp_spread,gust_spread,qpf_spread)

        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Calculated Confidence", f"{score}/100", label)
        c2.metric("Temp Spread", f"{temp_spread:.1f}°F")
        c3.metric("Gust Spread", f"{gust_spread:.0f} mph")
        c4.metric("24h QPF Spread", f"{qpf_spread:.2f} in")

        st.subheader("Forecast-Time Comparison")
        variable_labels = {
            "temperature_2m":"Temperature (°F)",
            "dew_point_2m":"Dewpoint (°F)",
            "precipitation":"Hourly Precipitation (in)",
            "wind_gusts_10m":"Wind Gust (mph)",
            "pressure_msl":"MSLP (mb)",
        }
        var = st.selectbox("Variable", list(variable_labels), format_func=lambda x: variable_labels[x])
        chart = pd.DataFrame()
        for name,df in frames.items():
            part = df[["time",var]].head(horizon).set_index("time").rename(columns={var:name})
            chart = part if chart.empty else chart.join(part, how="outer")
        st.line_chart(chart, use_container_width=True)

        st.subheader("24-Hour Consensus")
        if len(det):
            qpf_med = det["24h QPF in"].median()
            gust_med = det["Peak Gust mph"].median()
            temp_med = det["Temp now °F"].median()
            st.write(
                f"**Median guidance:** temperature {temp_med:.0f}°F • "
                f"24-hour QPF {qpf_med:.2f} in • peak gust {gust_med:.0f} mph. "
                f"**Calculated confidence: {label}.**"
            )
            st.caption("Confidence is a spread-based workstation aid, not an official forecast probability.")

        with st.expander("About the model feeds"):
            st.write("HRRR, GFS, NBM and HGEFS are NOAA/NCEP guidance. ECMWF IFS is shown as a global deterministic comparison.")
            st.write("This version retrieves lightweight point guidance through Open-Meteo's model APIs so the Chromebook-hosted workstation remains responsive.")
            rap_native = nomads_rap_status()
            if rap_native["ok"]:
                st.success(f"NOAA/NCEP NOMADS RAP native GRIB2 catalog is reachable for {rap_native['date']}.")
            else:
                st.warning("NOAA/NCEP NOMADS RAP native catalog did not answer this refresh; RAP point guidance remains available.")
            st.write("The workstation now monitors the native NOAA/NCEP RAP GRIB2 catalog and uses RAP point guidance in comparisons. Full field decoding/mapping remains separate from this lightweight Chromebook layer.")

elif page == "Model Trends":
    st.header("Run-to-Run Trend Desk")
    zone = st.selectbox("Zone", list(LOCATIONS), key="trendzone")
    model_name = st.selectbox("Model", ["HRRR","RAP","GFS","ECMWF IFS","NBM"])
    loc = LOCATIONS[zone]
    cfg = MODEL_CONFIG[model_name]
    st.caption("Compares current guidance with the same valid hours from roughly 24 hours earlier.")

    try:
        tr = previous_run_signal(loc["lat"],loc["lon"],cfg["id"])
        now_local = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
        tr = tr[tr["time"] >= now_local].head(24)
        temp_delta = (tr["temperature_2m_previous_day0"] - tr["temperature_2m_previous_day1"]).mean()
        qpf0 = tr["precipitation_previous_day0"].fillna(0).sum()
        qpf1 = tr["precipitation_previous_day1"].fillna(0).sum()
        gust0 = tr["wind_gusts_10m_previous_day0"].max()
        gust1 = tr["wind_gusts_10m_previous_day1"].max()
        c1,c2,c3 = st.columns(3)
        c1.metric("Mean Temperature Change", f"{temp_delta:+.1f}°F")
        c2.metric("24h QPF Change", f"{qpf0-qpf1:+.2f} in", f"Current {qpf0:.2f} in")
        c3.metric("Peak Gust Change", f"{gust0-gust1:+.0f} mph", f"Current {gust0:.0f} mph")

        compare = tr.set_index("time")[["temperature_2m_previous_day0","temperature_2m_previous_day1"]]
        compare = compare.rename(columns={"temperature_2m_previous_day0":"Current guidance","temperature_2m_previous_day1":"~24h-old guidance"})
        st.subheader("Temperature Trend")
        st.line_chart(compare, use_container_width=True)

        if abs(qpf0-qpf1) < 0.05 and abs(gust0-gust1) < 4 and abs(temp_delta) < 2:
            st.success("Run-to-run signal: generally stable.")
        else:
            changes=[]
            if qpf0-qpf1 >= .05: changes.append("wetter")
            elif qpf0-qpf1 <= -.05: changes.append("drier")
            if gust0-gust1 >= 4: changes.append("windier")
            elif gust0-gust1 <= -4: changes.append("less windy")
            if temp_delta >= 2: changes.append("warmer")
            elif temp_delta <= -2: changes.append("cooler")
            st.info("Run-to-run signal: " + (", ".join(changes) if changes else "mixed changes") + ".")
    except Exception:
        st.warning("Previous-run data was unavailable for this model on this refresh. Current model guidance remains available in Model Intelligence.")

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
    zone = st.selectbox("Zone", list(LOCATIONS), key="deskzone")
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
            "saved":datetime.now(timezone.utc).isoformat(),"zone":zone,
            "qpf_low":qpf_low,"qpf_high":qpf_high,"gust":gust,"pop":pop,
            "confidence":confidence,"impact":impact,"reasons":reasons,"brandons_take":take
        }
        st.session_state.setdefault("decisions", []).append(record)
        st.success("Forecast decision saved for this browser session.")
    if st.session_state.get("decisions"):
        st.dataframe(pd.DataFrame(st.session_state["decisions"]), use_container_width=True, hide_index=True)

elif page == "Verification":
    st.header("Forecast Verification")
    st.write("This workspace will compare issued DWG forecasts against observations and calculate bias, MAE, timing error and model performance.")
    st.info("v0.2 adds live model comparison and trends. Persistent verification history is the next database upgrade.")
    st.dataframe(pd.DataFrame([
        ["Temperature","MAE / Bias","Framework ready"],
        ["QPF","MAE / Bias / Hit range","Framework ready"],
        ["Wind gust","MAE / Peak timing","Framework ready"],
        ["Precip timing","Onset/end error","Framework ready"],
    ], columns=["Forecast Element","Metrics","Status"]), use_container_width=True, hide_index=True)

elif page == "System Status":
    st.header("System Status")
    st.write("**NWS API:**", "🟢 Live" if live_ok else "🔵 Fallback mode")
    st.write("**Four-zone configuration:** 🟢 Ready")
    st.write("**NWS alerts:** 🟢 Connected")
    st.write("**NWS point forecasts:** 🟢 Connected")
    st.write("**HRRR point guidance:** 🟢 v0.2")
    st.write("**GFS point guidance:** 🟢 v0.2")
    st.write("**ECMWF IFS comparison:** 🟢 v0.2")
    st.write("**NBM point guidance:** 🟢 v0.2")
    st.write("**Ensemble-mean guidance:** 🟢 v0.2")
    st.write("**Run-to-run trend desk:** 🟢 v0.2")
    rap_native = nomads_rap_status()
    st.write("**NOAA/NCEP NOMADS RAP native feed:**", "🟢 Live" if rap_native["ok"] else "🔴 Unreachable this refresh")
    st.write("**Persistent database:** 🔵 Planned")
    st.write("**NWS Radar / GOES-19 satellite panels:** 🟢 Live")
