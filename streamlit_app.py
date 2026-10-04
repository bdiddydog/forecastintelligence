import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="DWG Forecast Intelligence", page_icon="🌦️", layout="wide")

APP_VERSION = "0.4"
LOCATIONS = {
    "Northern Delaware": {"city":"Wilmington","lat":39.7391,"lon":-75.5398},
    "Central Delaware": {"city":"Dover","lat":39.1582,"lon":-75.5244},
    "Inland Sussex": {"city":"Georgetown","lat":38.6901,"lon":-75.3855},
    "Delaware Beaches": {"city":"Rehoboth Beach","lat":38.7209,"lon":-75.0760},
}
DELAWARE_CITIES = {
    "Wilmington": (39.7391,-75.5398),
    "Newark": (39.6837,-75.7497),
    "New Castle": (39.6621,-75.5663),
    "Middletown": (39.4496,-75.7163),
    "Smyrna": (39.2998,-75.6046),
    "Dover": (39.1582,-75.5244),
    "Harrington": (38.9237,-75.5777),
    "Milford": (38.9126,-75.4283),
    "Seaford": (38.6412,-75.6110),
    "Georgetown": (38.6901,-75.3855),
    "Lewes": (38.7746,-75.1393),
    "Rehoboth Beach": (38.7209,-75.0760),
    "Bethany Beach": (38.5396,-75.0552),
    "Fenwick Island": (38.4604,-75.0541),
}
HEADERS = {"User-Agent": "DWG-Forecast-Intelligence/0.3 contact: Delaware Weather Guy"}

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

@st.cache_data(ttl=180)
def observation_explorer(lat, lon):
    meta = point_metadata(lat, lon)
    stations = get_json(meta["properties"]["observationStations"])["features"]
    if not stations:
        return None
    station = stations[0]
    sid = station["properties"]["stationIdentifier"]
    slat, slon = station["geometry"]["coordinates"][1], station["geometry"]["coordinates"][0]
    p = get_json(f"https://api.weather.gov/stations/{sid}/observations/latest")["properties"]

    def val(item):
        return None if not item else item.get("value")
    def ctof(v):
        return None if v is None else v*9/5+32
    def mph(item):
        v=val(item)
        if v is None: return None
        unit=item.get("unitCode","")
        if "km_h-1" in unit: return v*0.621371
        if "m_s-1" in unit: return v*2.23694
        return v
    def mb(item):
        v=val(item)
        if v is None: return None
        return v/100 if item.get("unitCode","").endswith(":Pa") else v
    def miles(item):
        v=val(item)
        if v is None: return None
        unit=item.get("unitCode","")
        return v/1609.344 if unit.endswith(":m") else v
    def rh_from_td(t,td):
        if t is None or td is None: return None
        import math
        return 100*math.exp((17.625*td)/(243.04+td))/math.exp((17.625*t)/(243.04+t))
    def distance_miles(a,b,c,d):
        import math
        R=3958.8
        p1,p2=math.radians(a),math.radians(c)
        dp=math.radians(c-a); dl=math.radians(d-b)
        h=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
        return 2*R*math.asin(math.sqrt(h))

    tc=val(p.get("temperature")); dc=val(p.get("dewpoint"))
    ts=p.get("timestamp")
    age=None
    if ts:
        try:
            age=max(0,int((datetime.now(timezone.utc)-datetime.fromisoformat(ts.replace("Z","+00:00"))).total_seconds()/60))
        except Exception: pass
    pressure=p.get("seaLevelPressure")
    if not pressure or val(pressure) is None:
        pressure=p.get("barometricPressure")
    return {
        "station":sid,
        "station_name":station["properties"].get("name",sid),
        "distance":distance_miles(lat,lon,slat,slon),
        "temp":ctof(tc),"dew":ctof(dc),"rh":rh_from_td(tc,dc),
        "wind":mph(p.get("windSpeed")),"gust":mph(p.get("windGust")),
        "dir":val(p.get("windDirection")),"pressure":mb(pressure),
        "visibility":miles(p.get("visibility")),
        "conditions":p.get("textDescription") or "—","time":ts,"age":age,
        "station_lat":slat,"station_lon":slon
    }

@st.cache_data(ttl=300)
def station_recent_observations(station_id):
    data=get_json(f"https://api.weather.gov/stations/{station_id}/observations?limit=12")
    rows=[]
    for feat in data.get("features",[]):
        p=feat["properties"]
        t=p.get("temperature",{}).get("value")
        d=p.get("dewpoint",{}).get("value")
        if t is not None:
            rows.append({"time":pd.to_datetime(p.get("timestamp")),"Temperature":t*9/5+32,
                         "Dewpoint":None if d is None else d*9/5+32})
    return pd.DataFrame(rows).sort_values("time") if rows else pd.DataFrame()

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


def load_zone_models(zone, days=3):
    loc = LOCATIONS[zone]
    frames = {}
    for name, cfg in MODEL_CONFIG.items():
        try:
            frames[name] = model_forecast(loc["lat"], loc["lon"], cfg["id"], days)
        except Exception:
            pass
    return frames

def current_future(df, hours=24):
    now_local = pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    future = df[df["time"] >= now_local].head(hours)
    return future if not future.empty else df.head(hours)

def precip_timing(df, threshold=0.005):
    f = current_future(df, 72)
    wet = f[f["precipitation"].fillna(0) >= threshold]
    if wet.empty:
        return "None", "None", "None"
    peak_i = wet["precipitation"].idxmax()
    return wet.iloc[0]["time"], df.loc[peak_i,"time"], wet.iloc[-1]["time"]

def arrow(delta, threshold):
    if delta > threshold: return "↑"
    if delta < -threshold: return "↓"
    return "→"

UPPER_LEVELS = [925,850,700,500,250]

@st.cache_data(ttl=900)
def upper_air_point(lat, lon, days=3):
    hourly=[]
    for lev in UPPER_LEVELS:
        hourly += [f"temperature_{lev}hPa",f"geopotential_height_{lev}hPa",
                   f"wind_speed_{lev}hPa",f"wind_direction_{lev}hPa"]
        if lev in [850,700]:
            hourly.append(f"relative_humidity_{lev}hPa")
    params={"latitude":lat,"longitude":lon,"hourly":",".join(hourly),
            "models":"ncep_gfs_global","forecast_days":days,
            "temperature_unit":"fahrenheit","wind_speed_unit":"mph",
            "timezone":"America/New_York"}
    data=get_json("https://api.open-meteo.com/v1/forecast",params=params,timeout=18)
    df=pd.DataFrame(data["hourly"]); df["time"]=pd.to_datetime(df["time"])
    return df

@st.cache_data(ttl=600)
def gfs_vorticity_native_status():
    now=datetime.now(timezone.utc)
    for offset in range(0,3):
        dt=now-pd.Timedelta(days=offset)
        day=dt.strftime("%Y%m%d")
        try:
            url=f"https://nomads.ncep.noaa.gov/cgi-bin/filter_gfs_0p25b.pl?dir=%2Fgfs.{day}"
            r=requests.get(url,headers=HEADERS,timeout=12)
            if r.ok:
                return {"ok":True,"date":day,"url":url}
        except Exception:
            pass
    return {"ok":False,"date":None,"url":"https://nomads.ncep.noaa.gov/"}

def discussion_seed(zone):
    loc=LOCATIONS[zone]
    obs=obs_data.get(zone,{})
    lines=[
        f"{zone} / {loc['city']}",
        f"Current conditions: {fmt(obs.get('temp'),0,'°F')}, dewpoint {fmt(obs.get('dew'),0,'°F')}, wind {fmt(obs.get('wind'),0,' mph')}.",
        "",
        "SYNOPSIS:",
        "",
        "MODEL / TREND DISCUSSION:",
        "",
        "TIMING:",
        "",
        "IMPACTS / DELAWARE DIFFERENCES:",
        "",
        "CONFIDENCE:",
        "",
        "BRANDON'S TAKE:"
    ]
    return "\n".join(lines)

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
    "Command Center","Delaware Weather Wall","Observations","Radar & Satellite","Upper Air",
    "Model Graphics","Model Battle Board","Discussion Desk","Forecast Guidance","Model Intelligence",
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

elif page == "Delaware Weather Wall":
    st.header("🗺️ Delaware Weather Wall")
    st.caption("One-screen situational awareness for the four DWG forecast zones.")

    map_rows=[]
    for zone,loc in LOCATIONS.items():
        o=obs_data[zone]
        map_rows.append({"lat":loc["lat"],"lon":loc["lon"],"Zone":zone,"Temperature":o["temp"] or 0,"Wind":o["wind"] or 0})
    st.map(pd.DataFrame(map_rows), latitude="lat", longitude="lon", size=80, zoom=7)

    cols=st.columns(4)
    for col,(zone,loc) in zip(cols,LOCATIONS.items()):
        o=obs_data[zone]
        with col:
            st.markdown('<div class="dwg-card">', unsafe_allow_html=True)
            st.markdown(f"#### {zone}")
            st.metric("Temperature",fmt(o["temp"],0,"°F"))
            st.metric("Dewpoint",fmt(o["dew"],0,"°F"))
            st.metric("Wind",fmt(o["wind"],0," mph"))
            st.write(f"**Pressure:** {fmt(o['pressure'],1,' mb')}")
            st.write(f"**Sky:** {o['text']}")
            st.markdown('</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("📍 Live Observation Explorer")
    st.caption("Choose a Delaware community. The explorer finds the nearest NWS observation station and tells you exactly where the reading came from.")

    ec1,ec2=st.columns([1,2])
    with ec1:
        city=st.selectbox("Check a location",list(DELAWARE_CITIES),key="obscity")
        clat,clon=DELAWARE_CITIES[city]
        try:
            ex=observation_explorer(clat,clon)
        except Exception:
            ex=None

        if ex:
            freshness="Fresh"
            if ex["age"] is not None and ex["age"]>60: freshness="Old"
            elif ex["age"] is not None and ex["age"]>30: freshness="Aging"
            st.markdown(f"### {city}")
            st.write(f"**Nearest station:** {ex['station']} — {ex['station_name']}")
            st.write(f"**Distance:** {ex['distance']:.1f} miles")
            st.write(f"**Observation age:** {ex['age']} min • {freshness}" if ex["age"] is not None else "**Observation age:** unavailable")
        else:
            st.error("The NWS observation feed did not return a station for this location.")

    with ec2:
        if ex:
            r1=st.columns(4)
            r1[0].metric("Temperature",fmt(ex["temp"],0,"°F"))
            r1[1].metric("Dewpoint",fmt(ex["dew"],0,"°F"))
            r1[2].metric("Humidity",fmt(ex["rh"],0,"%"))
            r1[3].metric("Visibility",fmt(ex["visibility"],1," mi"))
            r2=st.columns(4)
            r2[0].metric("Wind",fmt(ex["wind"],0," mph"))
            r2[1].metric("Gust",fmt(ex["gust"],0," mph"))
            r2[2].metric("Direction",fmt(ex["dir"],0,"°"))
            r2[3].metric("Pressure",fmt(ex["pressure"],1," mb"))
            st.info(f"**Current conditions:** {ex['conditions']}")

    if ex:
        try:
            recent=station_recent_observations(ex["station"])
            if not recent.empty:
                st.markdown("#### Recent Temperature / Dewpoint Trend")
                st.line_chart(recent.set_index("time")[["Temperature","Dewpoint"]],use_container_width=True)
        except Exception:
            st.caption("Recent trend data is temporarily unavailable.")

        station_map=pd.DataFrame([
            {"lat":clat,"lon":clon,"Location":city},
            {"lat":ex["station_lat"],"lon":ex["station_lon"],"Location":ex["station"]}
        ])
        st.caption("Map shows the selected community and its reporting observation station.")
        st.map(station_map,latitude="lat",longitude="lon",size=90,zoom=9)

    st.subheader("Statewide 24-Hour Model Snapshot")
    wall=[]
    with st.spinner("Building Delaware model snapshot…"):
        for zone in LOCATIONS:
            frames=load_zone_models(zone,2)
            for name in ["HRRR","RAP","GFS","ECMWF IFS","NBM"]:
                if name in frames:
                    sm=model_summary(frames[name])
                    wall.append({"Zone":zone,"Model":name,"QPF":sm.get("qpf24"),"Peak Gust":sm.get("gust24"),"Temp":sm.get("temp_now")})
    wdf=pd.DataFrame(wall)
    if not wdf.empty:
        zsum=wdf.groupby("Zone").agg({"QPF":"median","Peak Gust":"median","Temp":"median"}).reset_index()
        c1,c2=st.columns(2)
        with c1:
            st.markdown("**Median 24h QPF by zone**")
            st.bar_chart(zsum.set_index("Zone")[["QPF"]])
        with c2:
            st.markdown("**Median peak gust by zone**")
            st.bar_chart(zsum.set_index("Zone")[["Peak Gust"]])
        st.dataframe(zsum.rename(columns={"QPF":"24h QPF in","Peak Gust":"Peak Gust mph","Temp":"Temperature °F"}),use_container_width=True,hide_index=True)

elif page == "Radar & Satellite":
    st.header("📡 Radar & Satellite Lab")
    st.caption("Live operational imagery with Delaware-focused viewing.")
    radar_tab,sat_tab,split_tab=st.tabs(["Radar","Satellite","Split Screen"])
    with radar_tab:
        site=st.selectbox("Radar site",["KDOX — Dover, DE","KDIX — Philadelphia / Mt. Holly"],key="labsite")
        rid=site.split(" ")[0]
        st.image(f"https://radar.weather.gov/ridge/standard/{rid}_loop.gif",use_container_width=True)
        st.caption("NOAA/NWS RIDGE base reflectivity loop.")
        st.link_button("Open interactive NWS radar","https://radar.weather.gov/")
    with sat_tab:
        product=st.selectbox("GOES-East product",["GeoColor","Clean Longwave IR","Water Vapor"],key="labproduct")
        band={"GeoColor":"GEOCOLOR","Clean Longwave IR":"13","Water Vapor":"09"}[product]
        st.image(f"https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/{band}/1250x750.jpg",use_container_width=True)
        st.caption(f"NOAA/NESDIS GOES-19 {product}.")
    with split_tab:
        c1,c2=st.columns(2)
        with c1:
            st.markdown("**KDOX Radar**")
            st.image("https://radar.weather.gov/ridge/standard/KDOX_loop.gif",use_container_width=True)
        with c2:
            st.markdown("**GOES-19 GeoColor**")
            st.image("https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/1250x750.jpg",use_container_width=True)

elif page == "Upper Air":
    st.header("🌐 Upper Air Analysis")
    st.caption("GFS pressure-level guidance for Delaware plus direct NOAA/NCEP native vorticity access.")
    zone=st.selectbox("Delaware zone",list(LOCATIONS),key="upperzone")
    loc=LOCATIONS[zone]
    hour=st.select_slider("Forecast hour",options=[0,6,12,18,24,36,48,60,72],value=0)
    try:
        ua=upper_air_point(loc["lat"],loc["lon"],3)
        now_local=pd.Timestamp.now(tz="America/New_York").tz_localize(None)
        future=ua[ua["time"]>=now_local]
        row=future.iloc[min(hour,len(future)-1)] if len(future) else ua.iloc[0]
        valid=row["time"]
        st.write(f"**Valid:** {valid:%A %b %d • %I:%M %p} ET")
        tabs=st.tabs(["925 mb","850 mb","700 mb","500 mb","250 mb","Vorticity"])
        notes={
            925:"Low-level thermal field and boundary-layer flow.",
            850:"Low-level temperature/advection and moisture transport.",
            700:"Mid-level moisture and flow; useful for dry slots and forcing context.",
            500:"Primary synoptic steering level; troughs, ridges and shortwaves.",
            250:"Upper-level jet structure and high-level flow."
        }
        for tab,lev in zip(tabs[:5],UPPER_LEVELS):
            with tab:
                c1,c2,c3,c4=st.columns(4)
                c1.metric("Temperature",fmt(row.get(f"temperature_{lev}hPa"),0,"°F"))
                c2.metric("Height",fmt(row.get(f"geopotential_height_{lev}hPa"),0," m"))
                c3.metric("Wind",fmt(row.get(f"wind_speed_{lev}hPa"),0," mph"))
                c4.metric("Direction",fmt(row.get(f"wind_direction_{lev}hPa"),0,"°"))
                if lev in [850,700]:
                    st.metric("Relative Humidity",fmt(row.get(f"relative_humidity_{lev}hPa"),0,"%"))
                st.info(notes[lev])
                series=future.head(72)[["time",f"geopotential_height_{lev}hPa",f"wind_speed_{lev}hPa"]].set_index("time")
                st.markdown("#### Height trend")
                st.line_chart(series[[f"geopotential_height_{lev}hPa"]],use_container_width=True)
                st.markdown("#### Wind trend")
                st.line_chart(series[[f"wind_speed_{lev}hPa"]],use_container_width=True)
        with tabs[5]:
            native=gfs_vorticity_native_status()
            st.subheader("Absolute Vorticity — Native GFS")
            st.write("The native GFS secondary-variable GRIB2 feed carries **ABSV (absolute vorticity)** on pressure levels including 925, 850, 700, 500 and 250 mb.")
            if native["ok"]:
                st.success(f"NOAA/NCEP native GFS vorticity feed reachable • catalog {native['date']}")
            else:
                st.warning("Native GFS vorticity catalog did not answer this refresh.")
            st.markdown("**Operational emphasis:** 500-mb vorticity is the primary synoptic diagnostic here; 250 mb is better paired with jet/wind analysis, while 850/925 mb are usually more useful for thermal advection and low-level flow.")
            st.link_button("Open NOAA GFS GRIB Filter","https://nomads.ncep.noaa.gov/gribfilter.php?ds=gfs_0p25b")
            st.caption("Native vorticity field decoding/map rendering is intentionally separated from the lightweight point charts so the hosted app remains responsive.")
    except Exception as e:
        st.error("Upper-air point guidance is temporarily unavailable.")
        st.caption(str(e))

elif page == "Discussion Desk":
    st.header("📝 DWG Discussion Desk")
    st.caption("Forecast reasoning first. Live workstation data can seed the discussion; Brandon remains the forecaster of record.")

    discussion_type=st.tabs(["Daily Forecast","Severe / Hazards","Winter Weather","Coastal / Marine","Tropical","Model Discussion","Planning / Decisions"])
    if "discussion_store" not in st.session_state:
        st.session_state["discussion_store"]={}

    labels=["Daily Forecast","Severe / Hazards","Winter Weather","Coastal / Marine","Tropical","Model Discussion","Planning / Decisions"]
    for tab,label in zip(discussion_type,labels):
        with tab:
            k=label.replace(" ","_").replace("/","_")
            c1,c2,c3=st.columns([1,1,1])
            zone=c1.selectbox("Zone",["Statewide"]+list(LOCATIONS),key=f"z_{k}")
            confidence=c2.selectbox("Confidence",["Low","Moderate-Low","Moderate","Moderate-High","High"],index=2,key=f"c_{k}")
            impact=c3.selectbox("Impact",["Minimal","Low","Elevated","High","Extreme"],key=f"i_{k}")

            title=st.text_input("Discussion title",value=label,key=f"title_{k}")
            period=st.text_input("Forecast period",value="Next 24–72 hours",key=f"period_{k}")
            primary=st.text_input("Primary forecast concern",key=f"concern_{k}")
            changed=st.text_input("What changed since the previous forecast?",key=f"changed_{k}")

            seedzone=list(LOCATIONS)[0] if zone=="Statewide" else zone
            default=st.session_state["discussion_store"].get(k,discussion_seed(seedzone))
            body=st.text_area("Forecast discussion",value=default,height=360,key=f"body_{k}")

            key_messages=st.text_area("Key Messages",height=120,key=f"keys_{k}")
            delaware=st.text_area("Delaware Differences",height=120,key=f"de_{k}")
            decisions=st.text_area("Decision Impacts",height=120,key=f"decision_{k}")

            b1,b2,b3=st.columns(3)
            if b1.button("Save discussion",key=f"save_{k}",type="primary"):
                st.session_state["discussion_store"][k]=body
                st.success("Discussion saved for this browser session.")
            if b2.button("Refresh data starter",key=f"seed_{k}"):
                st.session_state["discussion_store"][k]=discussion_seed(seedzone)
                st.session_state[f"body_{k}"]=discussion_seed(seedzone)
                st.rerun()
            if b3.button("Clear draft",key=f"clear_{k}"):
                st.session_state["discussion_store"][k]=""
                st.session_state[f"body_{k}"]=""
                st.rerun()

            st.divider()
            st.markdown("#### Discussion Header Preview")
            st.write(f"**{title}**")
            st.write(f"**Forecast period:** {period} • **Confidence:** {confidence} • **Impact:** {impact}")
            if primary: st.write(f"**Primary concern:** {primary}")
            if changed: st.write(f"**What changed:** {changed}")
            st.caption(f"Updated {datetime.now(ZoneInfo('America/New_York')):%b %d, %Y • %I:%M %p %Z}")

elif page == "Model Graphics":
    st.header("📈 Model Graphics Center")
    st.caption("Time-series graphics for Delaware point guidance.")
    zone=st.selectbox("Zone",list(LOCATIONS),key="graphicszone")
    hours=st.select_slider("Forecast horizon",options=[12,24,36,48,72],value=48)
    frames=load_zone_models(zone,3)
    if not frames:
        st.error("No model feeds returned on this refresh.")
    else:
        tabs=st.tabs(["Temperature","QPF","Wind Gust","Dewpoint","MSLP"])
        specs=[
            ("temperature_2m","Temperature °F",False),
            ("precipitation","Hourly QPF in",True),
            ("wind_gusts_10m","Wind gust mph",False),
            ("dew_point_2m","Dewpoint °F",False),
            ("pressure_msl","MSLP mb",False)
        ]
        for tab,(var,label,bars) in zip(tabs,specs):
            with tab:
                chart=pd.DataFrame()
                for name,df in frames.items():
                    p=current_future(df,hours)[["time",var]].set_index("time").rename(columns={var:name})
                    chart=p if chart.empty else chart.join(p,how="outer")
                st.markdown(f"### {label}")
                if bars and len(chart.columns):
                    st.line_chart(chart,use_container_width=True)
                    st.caption("Each line is hourly model QPF; totals are summarized below.")
                else:
                    st.line_chart(chart,use_container_width=True)
        st.subheader("Model Summary Cards")
        cards=st.columns(min(3,max(1,len(frames))))
        for i,(name,df) in enumerate(frames.items()):
            sm=model_summary(df)
            with cards[i%len(cards)]:
                st.markdown('<div class="dwg-card">',unsafe_allow_html=True)
                st.markdown(f"**{name}**")
                st.write(f"24h QPF: **{fmt(sm.get('qpf24'),2,' in')}**")
                st.write(f"Peak gust: **{fmt(sm.get('gust24'),0,' mph')}**")
                st.write(f"Temperature: **{fmt(sm.get('temp_now'),0,'°F')}**")
                st.markdown('</div>',unsafe_allow_html=True)

elif page == "Model Battle Board":
    st.header("⚔️ Model Battle Board")
    st.caption("Consensus, spread, timing and outliers — one board.")
    zone=st.selectbox("Zone",list(LOCATIONS),key="battlezone")
    frames=load_zone_models(zone,3)
    rows=[]
    for name,df in frames.items():
        sm=model_summary(df)
        onset,peak,end=precip_timing(df)
        rows.append({"Model":name,"24h QPF":sm.get("qpf24"),"Peak Gust":sm.get("gust24"),
                     "Temp":sm.get("temp_now"),"Onset":onset,"Peak":peak,"End":end})
    bdf=pd.DataFrame(rows)
    if bdf.empty:
        st.error("No model guidance returned.")
    else:
        det=bdf[bdf["Model"].isin(["HRRR","RAP","GFS","ECMWF IFS","NBM"])].copy()
        qmed=det["24h QPF"].median()
        gmed=det["Peak Gust"].median()
        tmed=det["Temp"].median()
        qs=det["24h QPF"].max()-det["24h QPF"].min()
        gs=det["Peak Gust"].max()-det["Peak Gust"].min()
        ts=det["Temp"].max()-det["Temp"].min()
        score,label=confidence_from_spread(ts,gs,qs)
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Consensus QPF",fmt(qmed,2," in"))
        c2.metric("Consensus Gust",fmt(gmed,0," mph"))
        c3.metric("Consensus Temp",fmt(tmed,0,"°F"))
        c4.metric("Agreement",f"{score}/100",label)

        c1,c2=st.columns(2)
        with c1:
            st.markdown("### QPF Battle")
            st.bar_chart(det.set_index("Model")[["24h QPF"]])
        with c2:
            st.markdown("### Wind Battle")
            st.bar_chart(det.set_index("Model")[["Peak Gust"]])

        st.subheader("Timing Board")
        show=bdf.copy()
        for col in ["Onset","Peak","End"]:
            show[col]=show[col].apply(lambda x: x.strftime("%a %I %p") if hasattr(x,"strftime") else x)
        st.dataframe(show,use_container_width=True,hide_index=True)

        st.subheader("Outlier Check")
        notes=[]
        if len(det)>=3:
            for _,r in det.iterrows():
                if abs(r["24h QPF"]-qmed) > max(.15,qs*.45):
                    notes.append(f"{r['Model']} is an outlier on QPF ({r['24h QPF']:.2f} in vs {qmed:.2f} in median).")
                if abs(r["Peak Gust"]-gmed) > max(5,gs*.45):
                    notes.append(f"{r['Model']} is an outlier on gusts ({r['Peak Gust']:.0f} mph vs {gmed:.0f} mph median).")
        if notes:
            for n in notes: st.warning(n)
        else:
            st.success("No major deterministic outlier detected by the current spread rules.")

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
    st.info("v0.3 adds the Weather Wall, Radar/Satellite Lab, Model Graphics Center and Model Battle Board. Persistent verification history remains the next database upgrade.")
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
    st.write("**Run-to-run trend desk:** 🟢 v0.3")
    rap_native = nomads_rap_status()
    st.write("**NOAA/NCEP NOMADS RAP native feed:**", "🟢 Live" if rap_native["ok"] else "🔴 Unreachable this refresh")
    st.write("**Persistent database:** 🔵 Planned")
    st.write("**Delaware Weather Wall:** 🟢 v0.3")
    st.write("**Live Observation Explorer:** 🟢 v0.3")
    st.write("**Radar / Satellite Lab:** 🟢 v0.3")
    st.write("**Model Graphics Center:** 🟢 v0.3")
    st.write("**Model Battle Board:** 🟢 v0.3")
    st.write("**Upper Air Analysis:** 🟢 v0.4")
    st.write("**Discussion Desk:** 🟢 v0.4")
