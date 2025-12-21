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
import rasterio
from rasterio.plot import show
import matplotlib.pyplot as plt

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")

st.info(
    "⚠️ Surveillance régionale du CH₄ à partir de données satellitaires (Sentinel-5P). "
    "Ce système ne remplace pas les inspections terrain."
)

# ===================== GEE INIT =====================
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

# ===================== SITE INPUT =====================
st.sidebar.header("📍 Paramètres du site")
latitude = st.sidebar.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.sidebar.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.sidebar.text_input("Nom du site", "Hassi R'mel")

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

# ===================== SESSION STATE =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
    st.session_state.results = {}

# ===================== UTILS =====================
def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    raise ValueError(f"Aucune colonne CH4 trouvée : {list(df.columns)}")

# ===================== FUNCTIONS =====================
def get_latest_ch4(latitude, longitude, days_back=90):
    geom = ee.Geometry.Point([longitude, latitude]).buffer(3500)

    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    size = col.size().getInfo()
    if size == 0:
        return None, None

    imgs = col.toList(size)

    for i in range(size):
        img = ee.Image(imgs.get(i))
        date_img = ee.Date(
            img.get("system:time_start")
        ).format("YYYY-MM-dd").getInfo()

        ch4_dict = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=7000,
            maxPixels=1e9
        ).getInfo()

        val = ch4_dict.get("CH4_column_volume_mixing_ratio_dry_air")
        if val is not None:
            return val * 1000, date_img

    return None, None


def detect_anomaly_zscore(value, series):
    return (value - series.mean()) / series.std()

# ===================== ANALYSIS =====================
st.markdown("## 🔍 Analyse journalière CH₄")

if st.button("🚀 Lancer l’analyse"):
    ch4, date_img = get_latest_ch4(latitude, longitude)
    ch4_series = get_ch4_series(df_hist)

    if ch4 is None:
        st.warning("⚠️ Donnée satellite indisponible — utilisation historique CSV")
        ch4 = ch4_series.iloc[-1]
        date_img = "Historique CSV"

    z = detect_anomaly_zscore(ch4, ch4_series)

    if z > 3:
        risk = "Critique"
        decision = "🚨 Alerte HSE + inspection immédiate"
        color = "red"
    elif z > 2:
        risk = "Anomalie"
        decision = "⚠️ Inspection terrain recommandée"
        color = "orange"
    else:
        risk = "Normal"
        decision = "✅ Surveillance continue"
        color = "green"

    st.session_state.analysis_done = True
    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date_img": date_img
    }

# ===================== DISPLAY RESULTS =====================
if st.session_state.analysis_done:
    r = st.session_state.results

    st.success(f"📅 Source des données : {r['date_img']}")

    c1, c2 = st.columns(2)
    c1.metric("CH₄ (ppb)", round(r["ch4"], 1))
    c2.metric("Z-score", round(r["z"], 2))

    st.markdown(
        f"<h3 style='color:{r['color']}'>Niveau de risque : {r['risk']}</h3>"
        f"<b>Action recommandée :</b> {r['decision']}",
        unsafe_allow_html=True
    )

    # ===================== MAP =====================
    st.markdown("## 🗺️ Pixel Sentinel-5P")

    m = folium.Map(location=[latitude, longitude], zoom_start=6)

    folium.Circle(
        location=[latitude, longitude],
        radius=3500,
        color=r["color"],
        fill=True,
        fill_opacity=0.35,
        tooltip="Pixel Sentinel-5P"
    ).add_to(m)

    folium.Marker(
        [latitude, longitude],
        tooltip=site_name
    ).add_to(m)

    st_folium(m, width=750, height=450)

    if st.button("🔄 Réinitialiser l’analyse"):
        st.session_state.analysis_done = False
        st.session_state.results = {}

# ===================== GEOTIFF =====================
st.markdown("## 🔥 Carte anomalies CH₄ (GeoTIFF)")

year = st.selectbox("Choisir l’année", ["2020", "2021", "2022", "2023", "2024", "2025"])
tif_path = f"data/anomaly CH4/CH4_anomaly_{year}.tif"

if os.path.exists(tif_path):
    with rasterio.open(tif_path) as src:
        fig, ax = plt.subplots(figsize=(8, 6))
        show(src, ax=ax)
        ax.set_title(f"Anomalie CH₄ – {year}")
        st.pyplot(fig)
else:
    st.warning("GeoTIFF non disponible pour cette année")

# ===================== LIMITS =====================
st.markdown("## ⚠️ Limites du système")
st.write("""
- Résolution spatiale kilométrique (Sentinel-5P)
- Sensibilité aux nuages et poussières
- Détection atmosphérique (pas localisation fuite)
- Validation terrain indispensable
""")

# ===================== ASSISTANT =====================
st.markdown("## 🤖 Assistant HSE intelligent")
question = st.text_input("Question CH₄ / HSE")

if st.button("Analyser la question"):
    if "anomalie" in question.lower():
        st.info("Les anomalies sont détectées par comparaison statistique à l’historique.")
    elif "satellite" in question.lower():
        st.info("Sentinel-5P assure une surveillance régionale quotidienne.")
    else:
        st.info("Analyse basée sur télédétection et règles HSE.")
