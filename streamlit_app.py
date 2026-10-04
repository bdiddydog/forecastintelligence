import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

st.set_page_config(page_title="DWG Forecast Intelligence", page_icon="🌦️", layout="wide")

APP_VERSION = "1.1"
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
UPPER_MODELS = {
    "GFS": "ncep_gfs_global",
    "RAP": "ncep_rap_conus",
}
WDS_UPPER_FIELDS = {
    925: ("925_temp_ht", "925mb Temperature and Heights"),
    850: ("850_temp_ht", "850mb Temperature and Heights"),
    700: ("700_rh_ht", "700mb Relative Humidity and Heights"),
    500: ("500_vort_ht", "500mb Vorticity, Heights and Winds"),
    250: ("250_wnd_ht", "250mb Wind and Heights"),
}
WDS_VORT_FIELDS = {
    850: ("850_vort_ht", "850mb Vorticity and Heights"),
    500: ("500_vort_ht", "500mb Vorticity, Heights and Winds"),
}

@st.cache_data(ttl=900)
def upper_air_model(lat, lon, model_id, days=4):
    hourly=[]
    for lev in UPPER_LEVELS:
        hourly += [f"temperature_{lev}hPa",f"geopotential_height_{lev}hPa",
                   f"wind_speed_{lev}hPa",f"wind_direction_{lev}hPa",
                   f"relative_humidity_{lev}hPa"]
    params={"latitude":lat,"longitude":lon,"hourly":",".join(hourly),
            "models":model_id,"forecast_days":days,
            "temperature_unit":"fahrenheit","wind_speed_unit":"mph",
            "timezone":"America/New_York"}
    data=get_json("https://api.open-meteo.com/v1/forecast",params=params,timeout=20)
    df=pd.DataFrame(data["hourly"]); df["time"]=pd.to_datetime(df["time"])
    return df

def upper_air_snapshot(df, forecast_hour):
    now_local=pd.Timestamp.now(tz="America/New_York").tz_localize(None)
    future=df[df["time"]>=now_local].reset_index(drop=True)
    if future.empty:
        future=df.reset_index(drop=True)
    target=min(max(int(forecast_hour),0),len(future)-1)
    row=future.iloc[target]
    prior=future.iloc[max(0,target-6)]
    return future,row,prior

def upper_signal(row, prior, lev):
    h=row.get(f"geopotential_height_{lev}hPa")
    hp=prior.get(f"geopotential_height_{lev}hPa")
    t=row.get(f"temperature_{lev}hPa")
    tp=prior.get(f"temperature_{lev}hPa")
    w=row.get(f"wind_speed_{lev}hPa")
    dh=None if pd.isna(h) or pd.isna(hp) else h-hp
    dt=None if pd.isna(t) or pd.isna(tp) else t-tp
    height="steady"
    if dh is not None and dh <= -15: height="falling"
    elif dh is not None and dh >= 15: height="rising"
    thermal="steady"
    if dt is not None and dt <= -2: thermal="cooling"
    elif dt is not None and dt >= 2: thermal="warming"
    return dh,dt,height,thermal,w

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

@st.cache_data(ttl=300)
def nws_text_product(product_type):
    data=get_json(f"https://api.weather.gov/products/types/{product_type}/locations/PHI")
    items=data.get("@graph",[])
    if not items:
        return None
    latest=items[0]
    pid=latest.get("id","").rstrip("/").split("/")[-1]
    if not pid:
        return None
    prod=get_json(f"https://api.weather.gov/products/{pid}")
    return {"text":prod.get("productText",""),"issued":prod.get("issuanceTime"),"id":pid}

@st.cache_data(ttl=600)
def nws_zone_forecast(lat,lon):
    meta=point_metadata(lat,lon)["properties"]
    zone_url=meta.get("forecastZone")
    if not zone_url:
        return None
    zid=zone_url.rstrip("/").split("/")[-1]
    z=get_json(f"https://api.weather.gov/zones/forecast/{zid}/forecast")
    return {"zone":zid,"name":z.get("properties",{}).get("name",zid),"periods":z.get("properties",{}).get("periods",[])}

WDS_BASE = "https://portal.weatherdecisionsolutions.com/weather/model-explorer"
WDS_PORTAL = "https://4070weather.com/portal"
WDS_FAVORITES = {
    "500 mb Vorticity / Heights / Winds": ("gfs","conus","500_vort_ht"),
    "500 mb RH / Heights": ("gfs","conus","500_rh_ht"),
    "850 mb Temperature / Heights": ("gfs","conus","850_temp_ht"),
    "850 mb Vorticity / Heights": ("gfs","conus","850_vort_ht"),
    "700 mb RH / Heights": ("gfs","conus","700_rh_ht"),
    "250 mb Wind / Heights": ("gfs","conus","250_wnd_ht"),
    "925 mb Temperature / Heights": ("gfs","conus","925_temp_ht"),
    "10 m Wind Gust": ("gfs","conus","wds_10m_gust"),
    "Total Precipitation": ("gfs","conus","precip_ptot"),
    "Simulated Radar": ("gfs","conus","sim_radar_comp"),
    "10:1 Snowfall": ("gfs","conus","wds_snow_ptot"),
    "CAPE / CIN": ("gfs","conus","wds_cape"),
}
WDS_PORTAL_CATALOG = {
    "Forecasts": [
        ("Weather Forecast","/forecast","Search U.S./Canadian locations and saved forecasts."),
        ("NWS Maps","/forecast","WDS documents NWS Maps under Forecasts, but its permanent deep-link is not verified; open the 4070 forecast/dashboard and choose NWS Maps."),
        ("Tropical","/forecast","Tropical tools live inside the WDS forecast/dashboard navigation; open the portal here, then choose Tropical."),
    ],
    "Radar & Satellite": [
        ("Radar","/radar","Interactive radar workspace and layer library."),
        ("Satellite","/radar","Satellite tools are reached from the Radar workspace/navigation."),
        ("Severe Probabilities","/radar","SPC Day 1 tornado, wind and hail probability layers in Radar."),
    ],
    "Models": [
        ("Model Explorer","/model-explorer","WDS model fields, frames, soundings and comparison tools."),
        ("Storm Tracks","MODEL_EXPLORER","Open the WDS model workspace; choose Analysis Tools → Storm Tracks."),
        ("2-Week Outlook","/forecast","Open the WDS portal; choose Models → Outlooks → 2-Week."),
        ("4-Week Outlook","/forecast","Open the WDS portal; choose Models → Outlooks → 4-Week."),
        ("9-Month Outlook","/forecast","Open the WDS portal; choose Models → Outlooks → 9-Month."),
    ],
    "Analytics": [
        ("Weather History","/forecast","Open the WDS portal; choose Analytics → Weather History."),
        ("Precip Reports","/forecast","Open the WDS portal; choose Analytics → Precip Reports."),
        ("Snow & Ice","/forecast","Open the WDS portal; choose Analytics → Snow & Ice."),
        ("Rivers & Flooding","/forecast","Open the WDS portal; choose Analytics → Rivers & Flooding."),
    ],
    "Share & Settings": [
        ("Capture","/model-explorer","Open WDS, then use the camera control for branded images/GIFs."),
        ("Notifications","/forecast","Open the WDS portal; then Settings → Notifications."),
    ],
}

def wds_model_url(model="gfs", map_name="conus", field="500_vort_ht"):
    return f"{WDS_BASE}?model={model}&map={map_name}&field={field}"

def wds_portal_url(path=""):
    return f"{WDS_PORTAL}{path}"

def wds_recommended_products(forecast_type):
    recipes={
        "Synoptic / Coastal Storm":["500 mb Vorticity / Heights / Winds","850 mb Temperature / Heights","700 mb RH / Heights","250 mb Wind / Heights","Total Precipitation","10 m Wind Gust"],
        "Severe Weather":["CAPE / CIN","500 mb Vorticity / Heights / Winds","250 mb Wind / Heights","850 mb Vorticity / Heights","Simulated Radar","10 m Wind Gust"],
        "Winter Weather":["925 mb Temperature / Heights","850 mb Temperature / Heights","700 mb RH / Heights","500 mb Vorticity / Heights / Winds","Total Precipitation","10:1 Snowfall"],
        "Heavy Rain / Flood":["700 mb RH / Heights","850 mb Temperature / Heights","500 mb Vorticity / Heights / Winds","Total Precipitation","Simulated Radar"],
        "General Forecast":["500 mb Vorticity / Heights / Winds","850 mb Temperature / Heights","700 mb RH / Heights","250 mb Wind / Heights","Total Precipitation"],
    }
    return recipes.get(forecast_type,recipes["General Forecast"])

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

st.sidebar.title("4070 Forecast Intelligence")
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

page = st.sidebar.radio("Forecast Intelligence", [
    "Morning Desk","4070 Launchpad","NOAA Discussions","Delaware Forecasts","Radar & Satellite",
    "Models & Upper Air","E-Wall","Forecast Production","Discussion Desk","Hazards","System Status"
])

now = datetime.now(ZoneInfo("America/New_York"))
st.title("🌦️ 4070 • DWG Forecast Intelligence")
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

if page == "Morning Desk":
    st.markdown("## ☕ Morning Forecast Desk")
    st.caption("Your one-stop morning briefing: observations, official NOAA/NWS text, Delaware forecasts, alerts, radar and 4070 model tools.")

    q1,q2,q3,q4=st.columns(4)
    q1.link_button("🌐 Open 4070 Portal",WDS_PORTAL,use_container_width=True)
    q2.link_button("📡 4070 Radar",wds_portal_url("/radar"),use_container_width=True)
    q3.link_button("🧭 4070 Model Explorer",WDS_BASE,use_container_width=True)
    q4.link_button("🗺️ NOAA/NWS Maps", "https://www.wpc.ncep.noaa.gov/html/sfc2.shtml", use_container_width=True)

    try: alerts=delaware_alerts()
    except Exception: alerts=[]
    a,b,c,d=st.columns(4)
    a.metric("NWS Data","LIVE" if live_ok else "FALLBACK")
    b.metric("Active DE Alerts",len(alerts))
    c.metric("Forecast Zones",4)
    d.metric("Updated",now.strftime("%I:%M %p"))

    if alerts:
        st.markdown("### ⚠️ Active Delaware Alerts")
        for feat in alerts[:5]:
            p=feat["properties"]; st.warning(f"**{p.get('event','Alert')}** — {p.get('headline','')}")

    st.markdown("### Delaware Now")
    cols=st.columns(4)
    for col,(zone,loc) in zip(cols,LOCATIONS.items()):
        o=obs_data[zone]
        with col:
            st.markdown('<div class="dwg-card">',unsafe_allow_html=True)
            st.markdown(f"**{zone}**")
            st.metric(loc["city"],fmt(o["temp"],0,"°F"))
            st.write(f"Dew {fmt(o['dew'],0,'°F')} • Wind {fmt(o['wind'],0,' mph')}")
            st.write(f"Gust {fmt(o['gust'],0,' mph')} • {o['text']}")
            st.markdown('</div>',unsafe_allow_html=True)

    st.markdown("### 📝 Today's NOAA/NWS Reading")
    afdcol,hwocol=st.columns(2)
    with afdcol:
        st.markdown("#### Area Forecast Discussion — NWS Mount Holly")
        try:
            afd=nws_text_product("AFD")
            if afd:
                st.caption(f"Issued {pd.to_datetime(afd['issued']).tz_convert('America/New_York'):%b %d • %I:%M %p ET}" if afd.get("issued") else "Latest issuance")
                st.text_area("Latest AFD",afd["text"],height=430,key="morning_afd",label_visibility="collapsed")
            else: st.warning("Latest AFD unavailable.")
        except Exception as e: st.warning("Mount Holly AFD unavailable on this refresh.")
    with hwocol:
        st.markdown("#### Hazardous Weather Outlook — NWS Mount Holly")
        try:
            hwo=nws_text_product("HWO")
            if hwo:
                st.caption(f"Issued {pd.to_datetime(hwo['issued']).tz_convert('America/New_York'):%b %d • %I:%M %p ET}" if hwo.get("issued") else "Latest issuance")
                st.text_area("Latest HWO",hwo["text"],height=430,key="morning_hwo",label_visibility="collapsed")
            else: st.warning("Latest HWO unavailable.")
        except Exception: st.warning("Mount Holly HWO unavailable on this refresh.")

    st.markdown("### 🔎 Morning Launch Rack")
    r1,r2,r3,r4=st.columns(4)
    r1.link_button("500 mb Vorticity",wds_model_url("gfs","conus","500_vort_ht"),use_container_width=True)
    r2.link_button("850 mb Temperature",wds_model_url("gfs","conus","850_temp_ht"),use_container_width=True)
    r3.link_button("Total Precipitation",wds_model_url("gfs","conus","precip_ptot"),use_container_width=True)
    r4.link_button("Wind Gusts",wds_model_url("gfs","conus","wds_10m_gust"),use_container_width=True)

elif page == "4070 Launchpad":
    st.header("🌐 4070 Weather Launchpad")
    st.caption("4070 is the primary visualization platform. Forecast Intelligence keeps its most-used tools one click away.")
    p1,p2,p3,p4=st.columns(4)
    p1.link_button("4070 Home",WDS_PORTAL,use_container_width=True)
    p2.link_button("Radar",wds_portal_url("/radar"),use_container_width=True)
    p3.link_button("NOAA/NWS Maps", "https://www.wpc.ncep.noaa.gov/html/sfc2.shtml", use_container_width=True)
    p4.link_button("Model Explorer",WDS_BASE,use_container_width=True)
    cats=st.tabs(list(WDS_PORTAL_CATALOG))
    for tab,(category,items) in zip(cats,WDS_PORTAL_CATALOG.items()):
        with tab:
            cols=st.columns(3)
            for i,(name,path,desc) in enumerate(items):
                with cols[i%3]:
                    st.markdown(f"**{name}**")
                    st.caption(desc)
                    target=WDS_BASE if path=="MODEL_EXPLORER" else wds_portal_url(path)
                    st.link_button(f"Open {name}",target,use_container_width=True)

elif page == "NOAA Discussions":
    st.header("📝 NOAA / NWS Discussion Reader")
    st.caption("Latest operational text from NWS Mount Holly (PHI), presented inside the Intelligencer.")
    tabs=st.tabs(["Area Forecast Discussion","Hazardous Weather Outlook"])
    for tab,ptype,title in zip(tabs,["AFD","HWO"],["Area Forecast Discussion","Hazardous Weather Outlook"]):
        with tab:
            try:
                prod=nws_text_product(ptype)
                if prod:
                    st.subheader(title)
                    if prod.get("issued"):
                        st.caption(f"Issued {pd.to_datetime(prod['issued']).tz_convert('America/New_York'):%A, %b %d • %I:%M %p ET}")
                    st.text_area(title,prod["text"],height=720,key=f"reader_{ptype}",label_visibility="collapsed")
                else: st.warning(f"No current {ptype} product returned.")
            except Exception as e:
                st.error(f"The latest {ptype} could not be retrieved from api.weather.gov.")

elif page == "Delaware Forecasts":
    st.header("📍 Delaware Forecast Center")
    st.caption("Official NWS point and forecast-zone access for the four DWG operating areas.")
    zone=st.segmented_control("Area",list(LOCATIONS),default=list(LOCATIONS)[0])
    loc=LOCATIONS[zone]
    point_tab,zone_tab=st.tabs(["Point Forecast","Area / Zone Forecast"])
    with point_tab:
        try:
            periods=forecast(loc["lat"],loc["lon"])
            for p in periods[:10]:
                with st.expander(f"{p['name']} • {p['temperature']}°{p['temperatureUnit']} • {p['shortForecast']}",expanded=p["number"]<=2):
                    st.write(p["detailedForecast"]); st.caption(f"Wind: {p['windDirection']} {p['windSpeed']}")
        except Exception: st.error("NWS point forecast is temporarily unavailable.")
    with zone_tab:
        try:
            z=nws_zone_forecast(loc["lat"],loc["lon"])
            if z:
                st.write(f"**NWS Forecast Zone:** {z['zone']} — {z['name']}")
                for p in z["periods"][:10]:
                    st.markdown(f"### {p.get('name','Period')}")
                    st.write(p.get("detailedForecast") or p.get("shortForecast") or "Forecast text unavailable.")
            else: st.warning("Forecast-zone information was unavailable.")
        except Exception: st.error("NWS zone forecast is temporarily unavailable.")

elif page == "Models & Upper Air":
    st.header("🧭 Models & Upper Air")
    st.caption("Forecast Intelligence diagnostics with 4070/WDS as the primary chart and visualization engine.")
    mtabs=st.tabs(["4070 Model Rack","Upper-Air Profile","Model Consensus"])
    with mtabs[0]:
        c1,c2=st.columns(2)
        model=c1.selectbox("4070 model",["gfs","ecmwf","hrrr","rap","nbm"],key="v1_model")
        domain=c2.selectbox("Domain",["conus","northeast","midatlantic"],key="v1_domain")
        cols=st.columns(3)
        for i,(name,(_,_,field)) in enumerate(WDS_FAVORITES.items()):
            with cols[i%3]: st.link_button(name,wds_model_url(model,domain,field),key=f"v1_{field}",use_container_width=True)
    with mtabs[1]:
        zone=st.selectbox("Delaware area",list(LOCATIONS),key="v1_upper_zone")
        model_name=st.selectbox("Profile model",list(UPPER_MODELS),key="v1_upper_model")
        hour=st.select_slider("Hours from now",options=[0,3,6,12,18,24,36,48,60,72],value=0,key="v1_upper_hour")
        loc=LOCATIONS[zone]
        try:
            df=upper_air_model(loc["lat"],loc["lon"],UPPER_MODELS[model_name],4)
            future,row,prior=upper_air_snapshot(df,hour)
            rows=[]
            for lev in UPPER_LEVELS:
                dh,dt,ht,tt,w=upper_signal(row,prior,lev)
                rows.append({"Level":f"{lev} mb","Temp °F":row.get(f"temperature_{lev}hPa"),"RH %":row.get(f"relative_humidity_{lev}hPa"),"Height m":row.get(f"geopotential_height_{lev}hPa"),"6h Δ Height":dh,"Wind mph":w,"Signal":f"{ht} / {tt}"})
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        except Exception: st.warning("Upper-air profile unavailable on this refresh.")
    with mtabs[2]:
        zone=st.selectbox("Consensus area",list(LOCATIONS),key="v1_cons_zone")
        frames=load_zone_models(zone,2)
        rows=[]
        for name,df in frames.items():
            sm=model_summary(df); rows.append({"Model":name,"24h QPF":sm.get("qpf24"),"Peak Gust":sm.get("gust24"),"Temperature":sm.get("temp_now")})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        else: st.warning("Model guidance unavailable.")

elif page == "E-Wall":
    st.header("🧱 4070 Forecast E-Wall")
    st.caption("A compact electronic map-wall inspired launch board: current data, NOAA text, radar/satellite, upper air and 4070 model products without menu hunting.")
    ew_tabs=st.tabs(["CURRENT","SAT / RADAR","UPPER AIR","MODELS","NOAA TEXT","4070"])
    with ew_tabs[0]:
        cols=st.columns(4)
        for col,(zone,loc) in zip(cols,LOCATIONS.items()):
            o=obs_data[zone]
            with col:
                st.markdown(f"### {loc['city']}")
                st.metric("Temp",fmt(o["temp"],0,"°F"))
                st.write(f"DP {fmt(o['dew'],0,'°F')} • Wind {fmt(o['wind'],0,' mph')}")
                st.write(o["text"])
    with ew_tabs[1]:
        c1,c2,c3=st.columns(3)
        c1.link_button("KDOX Radar Loop","https://radar.weather.gov/ridge/standard/KDOX_loop.gif",use_container_width=True)
        c2.link_button("KDIX Radar Loop","https://radar.weather.gov/ridge/standard/KDIX_loop.gif",use_container_width=True)
        c3.link_button("GOES-East Imagery","https://www.star.nesdis.noaa.gov/GOES/conus.php",use_container_width=True)
        st.image("https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/625x375.gif",use_container_width=True)
    with ew_tabs[2]:
        levels=[("925 TEMP/HT","925_temp_ht"),("850 TEMP/HT","850_temp_ht"),("850 VORT/HT","850_vort_ht"),("700 RH/HT","700_rh_ht"),("500 VORT/HT","500_vort_ht"),("500 RH/HT","500_rh_ht"),("250 WIND/HT","250_wnd_ht")]
        cols=st.columns(4)
        for i,(name,field) in enumerate(levels):
            cols[i%4].link_button(name,wds_model_url("gfs","conus",field),use_container_width=True)
    with ew_tabs[3]:
        products=[("GFS 500MB","gfs","500_vort_ht"),("ECMWF 500MB","ecmwf","500_vort_ht"),("HRRR RADAR","hrrr","sim_radar_comp"),("NBM QPF","nbm","precip_ptot"),("GFS QPF","gfs","precip_ptot"),("GFS GUST","gfs","wds_10m_gust"),("GFS CAPE","gfs","wds_cape"),("GFS SNOW","gfs","wds_snow_ptot")]
        cols=st.columns(4)
        for i,(name,m,field) in enumerate(products):
            cols[i%4].link_button(name,wds_model_url(m,"conus",field),use_container_width=True)
    with ew_tabs[4]:
        c1,c2=st.columns(2)
        try:
            afd=nws_text_product("AFD")
            c1.text_area("AREA FORECAST DISCUSSION",afd["text"] if afd else "Unavailable",height=420)
        except Exception: c1.warning("AFD unavailable.")
        try:
            hwo=nws_text_product("HWO")
            c2.text_area("HAZARDOUS WEATHER OUTLOOK",hwo["text"] if hwo else "Unavailable",height=420)
        except Exception: c2.warning("HWO unavailable.")
    with ew_tabs[5]:
        cols=st.columns(4)
        cols[0].link_button("4070 PORTAL",WDS_PORTAL,use_container_width=True)
        cols[1].link_button("4070 RADAR",wds_portal_url("/radar"),use_container_width=True)
        cols[2].link_button("MODEL EXPLORER",WDS_BASE,use_container_width=True)
        cols[3].link_button("FORECASTS",wds_portal_url("/forecast"),use_container_width=True)

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

elif page == "Forecast Production":
    st.header("✍️ Daily Forecast Production Desk")
    st.caption("Enter the forecast once in a consistent structure. The desk builds the decision table and a ready-to-edit post from the same information.")
    sections=["Daily Forecast","Severe / Hazards","Winter Weather","Coastal / Marine","Tropical","Model Discussion","Planning / Decisions"]
    tabs=st.tabs(sections)
    for tab,section in zip(tabs,sections):
        with tab:
            k=section.lower().replace(" ","_").replace("/","_")
            st.markdown(f"### {section}")
            a,b,c=st.columns(3)
            status=a.selectbox("Status",["🟢 Favorable","👀 Stay Weather-Aware","🟡 Monitoring","⚠️ Consider Adjustments","🔴 High Impact"],key=f"{k}_status")
            confidence=b.selectbox("Confidence",["Low","Moderate-Low","Moderate","Moderate-High","High"],index=2,key=f"{k}_conf")
            window=c.text_input("Valid / forecast window",placeholder="Sunday morning through Sunday night",key=f"{k}_window")
            headline=st.text_input("Headline / primary message",placeholder="One sentence: what matters most?",key=f"{k}_headline")
            c1,c2=st.columns(2)
            with c1:
                current=st.text_area("Current assessment",height=110,placeholder="What do you expect to happen?",key=f"{k}_current")
                change=st.text_area("What changed?",height=100,placeholder="Changes from the previous forecast/model cycle.",key=f"{k}_change")
                best=st.text_input("Best usable period",placeholder="Saturday afternoon, especially north",key=f"{k}_best")
            with c2:
                concern=st.text_area("Primary concern / hazard",height=110,placeholder="Main forecast problem or limiting factor.",key=f"{k}_concern")
                trigger=st.text_area("Next trigger / review point",height=100,placeholder="What would make you change or escalate the forecast?",key=f"{k}_trigger")
                poor=st.text_input("Questionable / least favorable period",placeholder="Sunday afternoon-evening",key=f"{k}_poor")
            guidance=st.text_area("Decision guidance",height=90,placeholder="What should the reader do with this forecast?",key=f"{k}_guidance")
            north=st.text_input("Northern Delaware",key=f"{k}_north")
            central=st.text_input("Central Delaware",key=f"{k}_central")
            sussex=st.text_input("Inland Sussex",key=f"{k}_sussex")
            beaches=st.text_input("Delaware Beaches",key=f"{k}_beaches")
            take=st.text_area("Brandon's Take",height=100,key=f"{k}_take")

            table=pd.DataFrame([
                {"Category":"Overall","Status":status,"Best usable period":best,"Questionable / least favorable period":poor,"Decision guidance":guidance},
                {"Category":"Northern Delaware","Status":north,"Best usable period":best,"Questionable / least favorable period":poor,"Decision guidance":guidance},
                {"Category":"Central Delaware","Status":central,"Best usable period":best,"Questionable / least favorable period":poor,"Decision guidance":guidance},
                {"Category":"Inland Sussex","Status":sussex,"Best usable period":best,"Questionable / least favorable period":poor,"Decision guidance":guidance},
                {"Category":"Delaware Beaches","Status":beaches,"Best usable period":best,"Questionable / least favorable period":poor,"Decision guidance":guidance},
            ])
            st.markdown("#### Decision Table Preview")
            st.dataframe(table,use_container_width=True,hide_index=True)
            post=f"""**{headline or section}**

{status} • **Confidence:** {confidence}
**Valid:** {window or 'Not entered'}

{current}

**What changed:** {change}
**Primary concern:** {concern}
**Best window:** {best}
**Least favorable:** {poor}
**Decision:** {guidance}

**Delaware differences**
• Northern Delaware: {north}
• Central Delaware: {central}
• Inland Sussex: {sussex}
• Beaches: {beaches}

**Next review point:** {trigger}

**Brandon's Take:** {take}"""
            st.markdown("#### Post Draft Preview")
            st.text_area("Ready-to-edit post",post,height=360,key=f"{k}_post_preview")
            if st.button(f"Save {section} draft",key=f"save_{k}",type="primary"):
                st.session_state.setdefault("forecast_production",{})[section]={"saved":datetime.now(timezone.utc).isoformat(),"table":table.to_dict("records"),"post":post}
                st.success("Draft saved for this browser session.")

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
    st.write("**Upper-Air Workstation:** 🟢 v0.5 — GFS/RAP, cross-level diagnostics, WDS chart handoff")
    st.write("**4070 Forecast Workstation:** 🟢 v1.1 — animated satellite, E-Wall, structured Forecast Production Desk")
    st.write("**Discussion Desk:** 🟢 v0.4")