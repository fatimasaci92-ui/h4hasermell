# ===================== IMPORTS =====================
import streamlit as st
import ee
import json
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import math

# ===================== EARTH ENGINE INIT =====================
# ⚠️ AUTH STREAMLIT CLOUD (PAS ee.Authenticate)

if not ee.data._initialized:
    key = json.loads(st.secrets["EE_KEY_JSON"])
    credentials = ee.ServiceAccountCredentials(
        key["client_email"],
        key_data=json.dumps(key)
    )
    ee.Initialize(credentials)

# ===================== CONFIG =====================
st.set_page_config(layout="wide", page_title="CH₄ Attribution")

# ===================== FUNCTIONS =====================

def get_latest_ch4(lat, lon, days=60):
    geom = ee.Geometry.Point([lon, lat]).buffer(4000)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days, "day")

    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    if col.size().getInfo() == 0:
        return None, None

    imgs = col.toList(col.size())

    for i in range(col.size().getInfo()):
        img = ee.Image(imgs.get(i))

        val = img.reduceRegion(
            ee.Reducer.mean(),
            geom,
            scale=7000,
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

        if val is None:
            continue

        date_img = ee.Date(img.get("system:time_start")) \
            .format("YYYY-MM-dd").getInfo()

        return val * 1000, date_img  # ppb

    return None, None


def get_era5_wind(lat, lon):
    point = ee.Geometry.Point([lon, lat])
    date = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))

    img = (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .filterDate(date.advance(-1, "day"), date)
        .first()
    )

    u = img.select("u_component_of_wind_10m")
    v = img.select("v_component_of_wind_10m")

    vals = ee.Image.cat([u, v]).reduceRegion(
        ee.Reducer.mean(),
        point,
        scale=10000,
        maxPixels=1e9
    ).getInfo()

    if vals is None:
        return None, None

    u_val = vals.get("u_component_of_wind_10m")
    v_val = vals.get("v_component_of_wind_10m")

    if u_val is None or v_val is None:
        return None, None

    speed = math.sqrt(u_val**2 + v_val**2)
    direction = (math.degrees(math.atan2(u_val, v_val)) + 360) % 360

    return round(speed, 2), round(direction, 1)


def ch4_anomaly_map(lat, lon):
    geom = ee.Geometry.Point([lon, lat]).buffer(20000)

    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    recent = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(end.advance(-7, "day"), end)
        .mean()
    )

    climatology = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(end.advance(-60, "day"), end.advance(-7, "day"))
        .mean()
    )

    anomaly = recent.subtract(climatology)

    return anomaly.clip(geom)


# ===================== UI =====================
st.title("🛰️ Attribution des émissions de CH₄")

lat_site = st.number_input("Latitude", value=32.93, format="%.4f")
lon_site = st.number_input("Longitude", value=3.90, format="%.4f")

if st.button("🔍 Analyser"):
    with st.spinner("Analyse en cours..."):

        ch4, date_img = get_latest_ch4(lat_site, lon_site)
        wind_speed, wind_dir = get_era5_wind(lat_site, lon_site)

        col1, col2, col3 = st.columns(3)

        col1.metric("CH₄ (ppb)", "N/A" if ch4 is None else round(ch4, 1))
        col2.metric("Vent (m/s)", "N/A" if wind_speed is None else wind_speed)
        col3.metric("Direction (°)", "N/A" if wind_dir is None else wind_dir)

        if ch4 is not None:
            if ch4 > 1900 and wind_speed is not None and wind_speed > 4:
                source = "Transport par le vent (source distante)"
            elif ch4 > 1900:
                source = "Source locale probable (torche / fuite)"
            else:
                source = "Niveau normal"

            st.success(f"🧠 Interprétation : {source}")

        # ===================== MAP =====================
        m = folium.Map(location=[lat_site, lon_site], zoom_start=8)

        anomaly = ch4_anomaly_map(lat_site, lon_site)

        vis = {
            "min": -50,
            "max": 50,
            "palette": ["blue", "white", "red"]
        }

        folium.TileLayer(
            tiles=anomaly.getMapId(vis)["tile_fetcher"].url_format,
            attr="Sentinel-5P CH₄",
            name="Anomalie CH₄"
        ).add_to(m)

        folium.Marker(
            [lat_site, lon_site],
            tooltip="Site analysé",
            icon=folium.Icon(color="red")
        ).add_to(m)

        folium.LayerControl().add_to(m)

        st_folium(m, width=1100, height=600)

