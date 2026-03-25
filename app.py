# ================= app.py — VERSION COMPLÈTE FINALE + CARTE STABLE =================
import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium
import requests

# ================= INITIALISATION GOOGLE EARTH ENGINE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= CARBON MAPPER API =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= CACHE GLOBAL (CRITIQUE) =================
@st.cache_data(ttl=3600)
def cached_gee(latitude, longitude):
    return get_latest_ch4_from_gee(latitude, longitude)

@st.cache_data(ttl=3600)
def cached_carbon(lat, lon):
    return get_ch4_plumes_carbonmapper(lat, lon)

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= CHEMINS DES FICHIERS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"
csv_monthly = "data/2020 2024/CH4_HassiRmel_monthly_2020_2024.csv"

# ================= FONCTION GEE =================
def get_latest_ch4_from_gee(latitude, longitude, days_back=60):
    point = ee.Geometry.Point([longitude, latitude])
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(point)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    size = collection.size().getInfo()
    if size == 0:
        return None, None, True

    img = ee.Image(collection.first())

    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000,
        maxPixels=1e9
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    try:
        v = value.getInfo()
    except:
        return None, None, True

    ch4_ppb = float(v) * 1000
    today = datetime.utcnow().strftime("%Y-%m-%d")
    no_pass_today = date_img != today

    return ch4_ppb, date_img, no_pass_today

# ================= FONCTION CARBON MAPPER =================
def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"

    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {"gas": "CH4", "limit": 20}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)

        if response.status_code != 200:
            return []

        data = response.json()
        plumes = []

        for item in data.get("features", []):
            coords = item["geometry"]["coordinates"]
            props = item["properties"]

            plumes.append({
                "lat": coords[1],
                "lon": coords[0],
                "emission": props.get("emission_rate", 0)
            })

        return plumes

    except:
        return []

# ================= SECTION E : Analyse CH₄ du jour =================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE)")

if st.button("Analyser CH₄ du jour"):

    with st.spinner("Analyse en cours..."):

        ch4, date_img, no_pass_today = cached_gee(latitude, longitude)

        if ch4 is None:
            st.error("⚠️ Aucune image satellite disponible.")
            st.stop()

        st.success(f"CH₄ : **{ch4:.1f} ppb** ({date_img})")

        # ===== Carbon Mapper uniquement si besoin =====
        if ch4 >= 1850:
            plumes = cached_carbon(latitude, longitude)

            if len(plumes) > 0:
                st.error(f"{len(plumes)} plume(s) détectée(s)")
            else:
                st.success("Aucune fuite détectée")

# ================= SECTION H : CARTE STABLE =================
st.markdown("## 🗺️ Carte stable")

if "map" not in st.session_state:

    m = folium.Map(location=[latitude, longitude], zoom_start=8)

    # Marker site
    folium.Marker(
        [latitude, longitude],
        tooltip=site_name,
        icon=folium.Icon(color="black")
    ).add_to(m)

    # Charger plumes UNE FOIS
    plumes = cached_carbon(latitude, longitude)

    for plume in plumes:
        folium.CircleMarker(
            location=[plume["lat"], plume["lon"]],
            radius=6,
            color="purple",
            fill=True,
            fill_opacity=0.8,
            tooltip=f"{plume['emission']} kg/h"
        ).add_to(m)

    st.session_state.map = m

st_folium(st.session_state.map, width=900, height=550)
