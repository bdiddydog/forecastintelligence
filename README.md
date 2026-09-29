# DWG Forecast Intelligence v0.1

A runnable first release of the Delaware Weather Guy forecasting workstation.

## What v0.1 does now

- Four Delaware forecast zones: Wilmington, Dover, Georgetown, Rehoboth Beach
- Live NWS observation retrieval using `api.weather.gov`
- Live Delaware NWS alerts
- Automatic fallback to demo data when a feed is unavailable
- HRRR / RAP / GFS / GEFS model-run discovery through Herbie
- Data-health oriented model status page
- Forecast Desk with Brandon's forecaster adjustment workflow
- Persistent forecast decision archive (CSV)
- Confidence-engine framework
- Verification workspace scaffold

## Why Herbie

Herbie provides one Python interface for discovering and reading HRRR, RAP, GFS, GEFS, NBM, RRFS and other GRIB2 datasets from multiple NOAA/cloud sources. That keeps DWG from being tied to a single download endpoint.

## Installation

Python 3.11+ is recommended.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run streamlit_app.py
```

Then open the local Streamlit address shown in the terminal, normally `http://localhost:8501`.

## If GRIB dependencies are difficult on Windows

The NWS portions of the dashboard can still run if you temporarily comment out the Herbie/cfgrib/eccodes lines in `requirements.txt`. The Model Status page will then report Herbie as unavailable instead of crashing the whole app.

For the full model system, Conda is often the easiest route:

```bash
conda create -n dwg python=3.11 -y
conda activate dwg
conda install -c conda-forge herbie-data cfgrib eccodes xarray pandas numpy -y
pip install streamlit plotly requests
streamlit run streamlit_app.py
```

## Architecture

- `app/services/nws.py` — NWS API ingestion
- `app/services/models.py` — model availability/discovery
- `app/engine/consensus.py` — consensus and confidence logic
- `app/config.py` — Delaware forecast zones
- `streamlit_app.py` — operational interface
- `data/forecaster_decisions.csv` — created when forecasts are saved

## v0.2 next

1. Extract HRRR/RAP/GFS/GEFS values at each Delaware forecast point.
2. Add forecast-hour time series for temperature, dewpoint, wind, QPF and pressure.
3. Add model consensus and run-to-run trend calculations using real model values.
4. Add completion validation for required forecast hours/variables.
5. Add NBM and optional ECMWF Open Data.
6. Add radar/MRMS and GOES panels.

## Important operational note

This workstation is decision support. Official watches, warnings and advisories should remain clearly identified as NWS products. Automated model guidance should not silently replace the human forecaster's issued forecast
