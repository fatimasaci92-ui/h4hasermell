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
st.info("⚠️ Surveillance régionale du CH₄ basée sur Sentinel-5P.")

# ===================== GEE INIT (CORRIGÉ) =====================
try:
    key_dict = json.loads(st.secrets["EE_KEY_JSON"])
    credentials = ee.ServiceAccountCredentials(
        key_dict["client_email"],
        key_data=json.dumps(key_dict)
    )
    ee.Initialize(credentials)
except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ===================== SIDEBAR =====================
st.sidebar.header("📍 Paramètres du site")
sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}
selected_site = st.sidebar.selectbox("Choisir le site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    raise ValueError("Aucune colonne CH4 détectée")

# ===================== FUNCTIONS =====================
def get_latest_ch4(lat, lon, days_back=60):
    geom = ee.Geometry.Point([lon, lat]).buffer(3500)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )
    if col.size().getInfo() == 0:
        return None, None
    img = ee.Image(col.first())
    val = img.reduceRegion(
    ee.Reducer.mean(),
    geom,
    7000,
    maxPixels=1e9
).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

# --- CORRECTION CRITIQUE ---
if val is None:
    return None, None

return val * 1000, date_img

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

# ===================== VIIRS TORCHES (CORRIGÉ) =====================
def get_active_flares(lat, lon, days_back=7):
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    fires = (
        ee.ImageCollection("NOAA/VIIRS/001/VNP14IMGTDL")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("Bright_ti4")
    )
    flares = fires.map(
        lambda img: img.gt(330).selfMask().reduceToVectors(
            geometry=geom,
            scale=375,
            geometryType="centroid",
            maxPixels=1e9
        )
    ).flatten()
    return flares

def count_flares(fc):
    try:
        return fc.size().getInfo()
    except:
        return 0

# ===================== ERA5 VENT =====================
def get_wind_speed(lat, lon):
    img = (
        ee.ImageCollection("ECMWF/ERA5_LAND/HOURLY")
        .select(["u_component_of_wind_10m", "v_component_of_wind_10m"])
        .sort("system:time_start", False)
        .first()
    )
    pt = ee.Geometry.Point([lon, lat])
    vals = img.reduceRegion(ee.Reducer.mean(), pt, 10000).getInfo()
    u = vals.get("u_component_of_wind_10m", 0)
    v = vals.get("v_component_of_wind_10m", 0)
    return np.sqrt(u**2 + v**2)

# ===================== ANALYSIS =====================
if st.button("🚀 Lancer l’analyse"):
    series = get_ch4_series(df_hist)
    ch4, date_img = get_latest_ch4(lat_site, lon_site)
    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "CSV"
    z = detect_anomaly(ch4, series)
    wind = get_wind_speed(lat_site, lon_site)
    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "wind": wind,
        "date": date_img
    }

# ===================== RESULTS =====================
if "results" in st.session_state:
    r = st.session_state.results
    c1, c2, c3 = st.columns(3)
    c1.metric("CH₄ (ppb)", round(r["ch4"], 1))
    c2.metric("Z-score", round(r["z"], 2))
    c3.metric("Vent (m/s)", round(r["wind"], 1))

    m = folium.Map(location=[lat_site, lon_site], zoom_start=7)
    folium.Circle([lat_site, lon_site], 3500, color="red", fill=True).add_to(m)

    # TORCHES
    flares = get_active_flares(lat_site, lon_site)
    n_flares = count_flares(flares)

    if n_flares > 0:
        st.success(f"🔥 Torches détectées : {n_flares}")
        fc = flares.getInfo()
        for f in fc["features"]:
            lon_f, lat_f = f["geometry"]["coordinates"]
            folium.Marker(
                [lat_f, lon_f],
                icon=folium.Icon(color="red", icon="fire"),
                tooltip="Torche VIIRS"
            ).add_to(m)
    else:
        st.warning("❓ Aucune torche détectée")

    st_folium(m, width=750, height=450)

# ===================== GRAPHIQUE =====================
st.markdown("## 📈 Évolution CH₄")
series = get_ch4_series(df_hist)
df_plot = df_hist.copy()
df_plot["CH4"] = series
df_plot["date"] = pd.to_datetime(df_plot.iloc[:, 0])
fig = px.line(df_plot, x="date", y="CH4")
if "results" in st.session_state:
    fig.add_scatter(
        x=[datetime.utcnow()],
        y=[st.session_state.results["ch4"]],
        mode="markers",
        marker=dict(color="red", size=12),
        name="Aujourd’hui"
    )
st.plotly_chart(fig, use_container_width=True)
