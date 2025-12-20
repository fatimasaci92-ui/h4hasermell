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
import matplotlib.pyplot as plt

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")

st.info(
"⚠️ Ce système permet une surveillance régionale du CH₄ à partir de données satellitaires "
"(Sentinel-5P). Il ne remplace pas les inspections terrain."
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
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", "Hassi R'mel")

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

# ===================== FUNCTIONS =====================

def get_latest_ch4(latitude, longitude, days_back=60):
geom = ee.Geometry.Point([longitude, latitude]).buffer(3500) # pixel TROPOMI
end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
start = end.advance(-days_back, "day")

col = (
ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
.filterBounds(geom)
.filterDate(start, end)
.select("CH4_column_volume_mixing_ratio_dry_air")
.sort("system:time_start", False)
)

img = ee.Image(col.first())
date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

ch4 = img.reduceRegion(
reducer=ee.Reducer.mean(),
geometry=geom,
scale=7000,
maxPixels=1e9
).getInfo()

if ch4 is None:
return None, None

return ch4 * 1000, date_img # ppb


def get_wind_speed(latitude, longitude, date):
point = ee.Geometry.Point([longitude, latitude])
era5 = (
ee.ImageCollection("ECMWF/ERA5/DAILY")
.filterDate(date, date)
.first()
)

u = era5.select("u_component_of_wind_10m")
v = era5.select("v_component_of_wind_10m")

wind = u.pow(2).add(v.pow(2)).sqrt()

speed = wind.reduceRegion(
reducer=ee.Reducer.mean(),
geometry=point,
scale=10000,
maxPixels=1e9
).getInfo()

return list(speed.values())[0]


def detect_anomaly_zscore(value, series):
mean = series.mean()
std = series.std()
z = (value - mean) / std
return z

# ===================== ANALYSIS =====================
st.markdown("## 🔍 Analyse journalière CH₄")

if st.button("Lancer l’analyse"):
ch4, date_img = get_latest_ch4(latitude, longitude)

if ch4 is None:
st.error("Aucune donnée CH₄ disponible.")
st.stop()

wind = get_wind_speed(latitude, longitude, date_img)
z = detect_anomaly_zscore(ch4, df_hist["CH4_ppb"])

# ===== DECISION LOGIC =====
if z > 3:
risk = "Critique"
decision = "Alerte HSE + inspection immédiate"
elif z > 2:
risk = "Anomalie"
decision = "Inspection terrain recommandée"
else:
risk = "Normal"
decision = "Surveillance continue"

st.success(f"📅 Date image : {date_img}")
st.metric("CH₄ (ppb)", round(ch4, 1))
st.metric("Z-score anomalie", round(z, 2))
st.metric("Vent moyen (m/s)", round(wind, 2))

st.warning(
f"⚠️ Anomalie atmosphérique détectée : **{risk}**\n\n"
f"➡️ Action recommandée : **{decision}**"
)

# ===================== MAP =====================
st.markdown("## 🗺️ Carte interactive")

m = folium.Map(location=[latitude, longitude], zoom_start=6)
folium.Circle(
location=[latitude, longitude],
radius=3500,
color="red",
fill=True,
fill_opacity=0.3,
tooltip="Pixel Sentinel-5P"
).add_to(m)

folium.Marker(
[latitude, longitude],
tooltip=site_name
).add_to(m)

st_folium(m, width=700, height=450)

# ===================== LIMITS =====================
st.markdown("## ⚠️ Limites du système")
st.write("""
- Résolution spatiale kilométrique (Sentinel-5P)
- Influence des conditions météorologiques
- Détection d’anomalies atmosphériques, pas de localisation précise de fuite
- Confirmation terrain indispensable
""")

# ===================== ASSISTANT =====================
st.markdown("## 🤖 Assistant HSE intelligent")
question = st.text_input("Question HSE / CH₄")

if st.button("Analyser la question"):
if "risque" in question.lower():
st.info("Le risque est évalué par détection d’anomalie statistique (z-score).")
elif "vent" in question.lower():
st.info("Le vent est utilisé pour réduire les faux positifs.")
else:
st.info("Analyse basée sur télédétection et règles HSE.")
