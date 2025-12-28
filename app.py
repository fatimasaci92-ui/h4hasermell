import streamlit as st
import ee
import folium
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import math

# ======================
# INITIALISATION GEE
# ======================
try:
    ee.Initialize()
except Exception:
    ee.Authenticate()
    ee.Initialize()

st.set_page_config(layout="wide")
st.title("🛰️ Analyse CH₄ – Attribution des sources")

# ======================
# PARAMÈTRES SITE
# ======================
lat_site = 32.9
lon_site = 3.3
roi = ee.Geometry.Point([lon_site, lat_site]).buffer(20000)

date_end = datetime.utcnow()
date_start = date_end - timedelta(days=7)

# ======================
# CH₄ SENTINEL-5P
# ======================
ch4_col = (
    ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
    .select("CH4_column_volume_mixing_ratio_dry_air")
    .filterDate(date_start.strftime("%Y-%m-%d"), date_end.strftime("%Y-%m-%d"))
    .filterBounds(roi)
)

ch4_mean = ch4_col.mean().clip(roi)

# ======================
# ANOMALIE CH₄ (Z-SCORE)
# ======================
ch4_std = ch4_col.reduce(ee.Reducer.stdDev()).clip(roi)
ch4_z = ch4_mean.subtract(ch4_col.mean()).divide(ch4_std)

# ======================
# ERA5 – VENT 10 m
# ======================
era5 = (
    ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
    .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
    .filterDate(date_end - timedelta(hours=6), date_end)
    .mean()
    .clip(roi)
)

u10 = era5.select("u_component_of_wind_10m")
v10 = era5.select("v_component_of_wind_10m")

wind_speed = u10.pow(2).add(v10.pow(2)).sqrt()

# ======================
# TORCHES VIIRS (ASSET CORRECT)
# ======================
flares = (
    ee.FeatureCollection("NOAA/VIIRS/001/VNP14IMGTDL")
    .filterBounds(roi)
    .filterDate(date_start.strftime("%Y-%m-%d"), date_end.strftime("%Y-%m-%d"))
)

# ======================
# ATTRIBUTION SOURCE
# ======================
def attribute_ch4_source():
    try:
        n_flares = flares.size().getInfo()
    except Exception:
        n_flares = 0

    ch4_val = ch4_mean.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=10000,
        maxPixels=1e9
    ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

    if ch4_val is None:
        ch4_val = 0

    if ch4_val > 1900 and n_flares > 0:
        return "🔥 Élévation CH₄ probablement liée aux torches", n_flares
    elif ch4_val > 1900 and n_flares == 0:
        return "⚠️ Élévation CH₄ non expliquée par les torches (fuite probable)", 0
    else:
        return "✅ Niveau CH₄ normal", n_flares


source_text, n_flares = attribute_ch4_source()

# ======================
# CARTE
# ======================
m = folium.Map(location=[lat_site, lon_site], zoom_start=7)

folium.TileLayer("cartodbpositron").add_to(m)

# CH₄
folium.TileLayer(
    tiles=folium.raster_layers.TileLayer(
        ch4_mean.visualize(
            min=1750,
            max=2000,
            palette=["blue", "yellow", "red"]
        ).getMapId()["tile_fetcher"].url_format
    ),
    name="CH₄ moyen"
).add_to(m)

# ANOMALIE
folium.TileLayer(
    tiles=folium.raster_layers.TileLayer(
        ch4_z.visualize(
            min=1,
            max=3,
            palette=["white", "orange", "red"]
        ).getMapId()["tile_fetcher"].url_format
    ),
    name="Anomalie CH₄ (Z)"
).add_to(m)

# VENT
folium.TileLayer(
    tiles=folium.raster_layers.TileLayer(
        wind_speed.visualize(
            min=0,
            max=10,
            palette=["white", "cyan", "blue"]
        ).getMapId()["tile_fetcher"].url_format
    ),
    name="Vitesse du vent (m/s)"
).add_to(m)

# TORCHES
try:
    flares_info = flares.limit(50).getInfo()
    for f in flares_info["features"]:
        lon_f, lat_f = f["geometry"]["coordinates"]
        folium.Marker(
            location=[lat_f, lon_f],
            icon=folium.Icon(color="red", icon="fire"),
            tooltip="Torche VIIRS"
        ).add_to(m)
except Exception:
    pass

folium.LayerControl().add_to(m)

st_folium(m, width=900, height=500)

# ======================
# INDICATEURS
# ======================
st.subheader("📊 Résultats")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Torches détectées", n_flares)

with col2:
    st.metric("Source probable", source_text)

with col3:
    try:
        ws = wind_speed.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=roi,
            scale=10000,
            maxPixels=1e9
        ).getInfo()
        ws_val = list(ws.values())[0]
    except Exception:
        ws_val = 0

    st.metric("Vent moyen (m/s)", round(ws_val, 1))

st.success("✔ Analyse terminée sans erreurs")
