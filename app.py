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

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")

# ===================== GEE INIT (SERVICE ACCOUNT) =====================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

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
            return pd.to_numeric(df[col], errors="coerce").dropna()
    raise ValueError("Colonne CH4 introuvable")

# ===================== GEE CH4 =====================
def get_latest_ch4(lat, lon, days_back=90):
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

    imgs = col.toList(col.size().getInfo())

    for i in range(col.size().getInfo()):
        img = ee.Image(imgs.get(i))
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

        val = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=7000,
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        val = ee.Number(val)

        try:
            val = val.getInfo()
            if val is not None:
                return float(val) * 1000, date_img
        except:
            pass

    return None, None

# ===================== ANOMALY =====================
def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

# ===================== VIIRS FLARES =====================
def get_active_flares(lat, lon):
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)

    fires = (
        ee.ImageCollection("NOAA/VIIRS/001/VNP14IMGTDL_NRT")
        .filterBounds(geom)
        .filterDate(
            ee.Date(datetime.utcnow().strftime("%Y-%m-%d")).advance(-7, "day"),
            ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
        )
        .select("Bright_ti4")
    )

    def extract(img):
        return img.gt(330).selfMask().reduceToVectors(
            geometry=geom,
            scale=375,
            geometryType="centroid",
            maxPixels=1e9
        )

    return fires.map(extract).flatten()

# ===================== SESSION =====================
if "done" not in st.session_state:
    st.session_state.done = False

# ===================== RUN =====================
if st.button("🚀 Lancer l’analyse"):
    ch4, date_img = get_latest_ch4(lat_site, lon_site)
    series = get_ch4_series(df_hist)

    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "CSV historique"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk = "Critique"
        color = "red"
        decision = "Alerte HSE immédiate"
    elif z > 2:
        risk = "Anomalie"
        color = "orange"
        decision = "Inspection terrain"
    else:
        risk = "Normal"
        color = "green"
        decision = "Surveillance continue"

    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date": date_img
    }

    st.session_state.done = True

# ===================== RESULTS =====================
if st.session_state.done:
    r = st.session_state.results

    st.metric("CH₄ (ppb)", round(r["ch4"], 1))
    st.metric("Z-score", round(r["z"], 2))
    st.markdown(f"### 🟢 Risque : **{r['risk']}**")
    st.info(r["decision"])

    # MAP
    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)

    folium.Circle(
        location=[lat_site, lon_site],
        radius=3500,
        color=r["color"],
        fill=True
    ).add_to(m)

    folium.Marker(
        location=[lat_site, lon_site],
        tooltip=selected_site
    ).add_to(m)

    # FLARES
    flares = get_active_flares(lat_site, lon_site)

    def add_flares(fc):
        def cb(fc_json):
            for f in fc_json["features"]:
                lon_f, lat_f = f["geometry"]["coordinates"]
                folium.Marker(
                    location=[lat_f, lon_f],
                    icon=folium.Icon(color="red", icon="fire"),
                    tooltip="Torche VIIRS"
                ).add_to(m)
        fc.evaluate(cb)

    add_flares(flares)

    st_folium(m, width=800, height=500)

# ===================== HISTORIQUE =====================
st.markdown("## 📈 Évolution historique CH₄")

series = get_ch4_series(df_hist)
df_plot = df_hist.copy()
df_plot["CH4"] = series
df_plot["date"] = pd.to_datetime(df_plot.iloc[:, 0])

fig = px.line(df_plot, x="date", y="CH4")
fig.add_hline(y=series.mean(), line_dash="dash")

if st.session_state.done:
    fig.add_scatter(
        x=[datetime.utcnow()],
        y=[st.session_state.results["ch4"]],
        mode="markers",
        marker=dict(size=12, color="red"),
        name="Analyse du jour"
    )

st.plotly_chart(fig, use_container_width=True)

