# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import ee
import json
import tempfile
import os
from datetime import datetime
import folium
from streamlit_folium import st_folium
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import smtplib
from email.mime.text import MIMEText

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")

# ===================== GEE INIT =====================
def get_active_flares(lat, lon, days_back=7):
    """
    Détection des torches / sources thermiques
    Dataset PUBLIC compatible Service Account
    """
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)

    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    fires = (
        ee.ImageCollection("NASA/VIIRS/002/VNP14A1")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("FireMask")
    )

    # FireMask == 7 → feu actif confirmé (torche / flare)
    def to_vectors(img):
        mask = img.eq(7)
        return mask.selfMask().reduceToVectors(
            geometry=geom,
            scale=1000,
            geometryType="centroid",
            maxPixels=1e9
        )

    flares = fires.map(to_vectors).flatten()

    # ⚠️ IMPORTANT : Streamlit → PAS de evaluate()
    try:
        features = flares.getInfo()["features"]
    except Exception:
        features = []

    return features


# ===================== SIDEBAR =====================
st.sidebar.header("📍 Site")
sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}
selected_site = st.sidebar.selectbox("Site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORICAL DATA =====================
df_hist = pd.read_csv("data/2020 2024/CH4_HassiRmel_2020_2024.csv")

def get_ch4_series(df):
    for c in df.columns:
        if "ch4" in c.lower():
            return df[c]
    raise ValueError("Colonne CH4 absente")

# ===================== CH4 TODAY =====================
def get_latest_ch4(lat, lon):
    geom = ee.Geometry.Point([lon, lat]).buffer(4000)
    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .sort("system:time_start", False)
        .limit(1)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )
    img = ee.Image(col.first())
    val = img.reduceRegion(
        ee.Reducer.mean(), geom, 7000, maxPixels=1e9
    ).getInfo()
    return val["CH4_column_volume_mixing_ratio_dry_air"] * 1000

# ===================== ERA5 WIND =====================
def get_wind(lat, lon):
    geom = ee.Geometry.Point([lon, lat])
    wind = (
        ee.ImageCollection("ECMWF/ERA5/DAILY")
        .select(["u_component_of_wind_10m","v_component_of_wind_10m"])
        .sort("system:time_start", False)
        .first()
    )
    data = wind.reduceRegion(
        ee.Reducer.mean(), geom, 10000, maxPixels=1e9
    ).getInfo()
    u, v = data["u_component_of_wind_10m"], data["v_component_of_wind_10m"]
    speed = np.sqrt(u**2 + v**2)
    direction = (270 - np.degrees(np.arctan2(v,u))) % 360
    return speed, direction

# ===================== VIIRS TORCHES (FIXED) =====================
def get_flares(lat, lon):
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)
    fires = (
        ee.ImageCollection("NASA/VIIRS/002/VNP14A1")
        .filterBounds(geom)
        .select("FireMask")
    )
    mask = fires.map(lambda i: i.eq(7))
    flares = mask.mean().selfMask().reduceToVectors(
        geometry=geom, scale=1000, geometryType="centroid"
    )
    return flares.getInfo()["features"]

# ===================== CH4 ANOMALY MAP =====================
def get_ch4_anomaly(lat, lon):
    geom = ee.Geometry.Point([lon, lat]).buffer(4000)
    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )
    mean = col.mean()
    std = col.reduce(ee.Reducer.stdDev())
    anomaly = col.sort("system:time_start", False).first().subtract(mean).divide(std)
    return anomaly

# ===================== ANALYSIS =====================
if st.button("🚀 Lancer l’analyse"):
    ch4 = get_latest_ch4(lat_site, lon_site)
    series = get_ch4_series(df_hist)
    z = (ch4 - series.mean()) / series.std()
    wind_speed, wind_dir = get_wind(lat_site, lon_site)
    flares = get_flares(lat_site, lon_site)

    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "wind_speed": wind_speed,
        "wind_dir": wind_dir,
        "n_flares": len(flares),
        "flares": flares
    }

# ===================== RESULTS =====================
if "results" in st.session_state:
    r = st.session_state.results

    st.metric("CH₄ (ppb)", round(r["ch4"],1))
    st.metric("Z-score", round(r["z"],2))
    st.metric("Vent (m/s)", round(r["wind_speed"],1))
    st.metric("Direction vent (°)", round(r["wind_dir"],0))

    # ===================== MAP =====================
    m = folium.Map(location=[lat_site, lon_site], zoom_start=7)

    for f in r["flares"]:
        lon_f, lat_f = f["geometry"]["coordinates"]
        folium.Marker(
            [lat_f, lon_f],
            icon=folium.Icon(color="red", icon="fire"),
            tooltip="Torche VIIRS"
        ).add_to(m)

    folium.Marker(
        [lat_site, lon_site],
        icon=folium.Icon(color="blue"),
        tooltip="Site"
    ).add_to(m)

    st_folium(m, width=800, height=500)

    # ===================== DECISION =====================
    if r["z"] > 2 and r["n_flares"] > 0:
        st.error("🔥 CH₄ élevé probablement dû aux torches")
    elif r["z"] > 2:
        st.warning("⚠️ CH₄ élevé – fuite possible (non liée aux torches)")
    else:
        st.success("✅ Situation normale")

# ===================== GRAPH =====================
df_plot = df_hist.copy()
df_plot["CH4"] = get_ch4_series(df_hist)
df_plot["date"] = pd.to_datetime(df_plot.iloc[:,0])
fig = px.line(df_plot, x="date", y="CH4")
st.plotly_chart(fig, use_container_width=True)
