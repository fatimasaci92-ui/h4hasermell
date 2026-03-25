# ================= app.py — VERSION FINALE STABLE =================
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

# ================= INITIALISATION GEE =================
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

CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")

st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INPUT =================
latitude = st.number_input("Latitude", value=32.93)
longitude = st.number_input("Longitude", value=3.30)
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= FONCTION GEE =================
def get_latest_ch4_from_gee(lat, lon):
    point = ee.Geometry.Point([lon, lat])
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(point)
        .sort("system:time_start", False)
    )

    img = ee.Image(collection.first())
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    try:
        ch4 = float(value.getInfo()) * 1000
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        return ch4, date_img
    except:
        return None, None

# ================= CARBON MAPPER CORRIGÉ =================
def get_ch4_plumes_carbonmapper(lat, lon, radius_km=50):

    if CARBON_API_TOKEN == "":
        st.warning("Token Carbon Mapper manquant")
        return []

    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"

    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {"gas": "CH4", "limit": 50}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)

        if response.status_code != 200:
            st.warning("API Carbon Mapper indisponible")
            return []

        data = response.json()
        plumes = []

        for item in data.get("features", []):
            coords = item["geometry"]["coordinates"]
            props = item["properties"]

            plume_lat = coords[1]
            plume_lon = coords[0]
            emission = props.get("emission_rate", 0)

            # Distance (km)
            dist = np.sqrt((plume_lat - lat)**2 + (plume_lon - lon)**2) * 111

            if dist <= radius_km:
                plumes.append({
                    "lat": plume_lat,
                    "lon": plume_lon,
                    "emission": emission,
                    "distance": round(dist, 2)
                })

        return plumes

    except Exception as e:
        st.error(f"Erreur Carbon Mapper : {e}")
        return []

# ================= ANALYSE JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour")

if st.button("Analyser"):
    ch4, date_img = get_latest_ch4_from_gee(latitude, longitude)

    if ch4:
        st.success(f"CH₄ : {ch4:.1f} ppb ({date_img})")

        if ch4 >= 1900:
            st.error("⚠️ Niveau critique")
        elif ch4 >= 1850:
            st.warning("⚠️ Niveau élevé")
        else:
            st.success("✅ Niveau normal")

# ================= CARTE STABLE =================
st.markdown("## 🗺️ Carte CH₄ + Carbon Mapper")

if "map" not in st.session_state:

    m = folium.Map(location=[latitude, longitude], zoom_start=8)

    # Site
    folium.Marker(
        [latitude, longitude],
        tooltip=site_name,
        icon=folium.Icon(color="black")
    ).add_to(m)

    # Plumes
    plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

    if len(plumes) > 0:
        st.error(f"{len(plumes)} plume(s) détectée(s)")

        for plume in plumes:
            folium.CircleMarker(
                location=[plume["lat"], plume["lon"]],
                radius=8,
                color="purple",
                fill=True,
                fill_opacity=0.9,
                tooltip=f"{plume['emission']} kg/h | {plume['distance']} km"
            ).add_to(m)
    else:
        st.success("Aucune plume détectée")

    folium.LayerControl().add_to(m)

    st.session_state.map = m

# Affichage stable
st_folium(st.session_state.map, width=900, height=550)
