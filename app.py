import streamlit as st
import ee
import geemap.foliumap as geemap
import folium
import requests
import json

# -------------------------------
# 🔐 INITIALISATION GEE
# -------------------------------
try:
    ee.Initialize()
except:
    ee.Authenticate()
    ee.Initialize()

# -------------------------------
# ⚙️ CONFIG APP
# -------------------------------
st.set_page_config(layout="wide")
st.title("🛰️ Surveillance CH4 - Hassi R'Mel")

# -------------------------------
# 📌 SESSION STATE (IMPORTANT)
# -------------------------------
if "map" not in st.session_state:
    st.session_state.map = None

if "result" not in st.session_state:
    st.session_state.result = None

# -------------------------------
# 🌍 ZONES
# -------------------------------
zones = {
    "Zone Nord": ee.Geometry.Polygon([
        [[3.185,33.013],[3.185,33.282],[3.810,33.278],[3.810,33.013]]
    ]),
    "Zone Centre": ee.Geometry.Polygon([
        [[3.4,33.1],[3.4,33.25],[3.7,33.25],[3.7,33.1]]
    ]),
    "Zone Sud": ee.Geometry.Polygon([
        [[3.3,32.9],[3.3,33.05],[3.8,33.05],[3.8,32.9]]
    ])
}

zone_name = st.selectbox("📍 Choisir une zone", list(zones.keys()))
zone = zones[zone_name]

# -------------------------------
# ⚡ CACHE GEE (CRITIQUE)
# -------------------------------
@st.cache_data(ttl=3600)
def get_ch4_data(geometry):
    collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4") \
        .select("CH4_column_volume_mixing_ratio_dry_air") \
        .filterDate("2024-01-01", "2024-12-31") \
        .filterBounds(geometry)

    image = collection.mean().clip(geometry)
    return image

# -------------------------------
# 🛰️ CARBON MAPPER (SIMULATION SAFE)
# -------------------------------
@st.cache_data(ttl=3600)
def get_carbon_mapper_data():
    try:
        url = "https://api.carbonmapper.org/api/v1/plumes"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            return response.json()
        else:
            return None
    except:
        return None

# -------------------------------
# ▶️ BOUTON ANALYSE
# -------------------------------
if st.button("🚀 Lancer l'analyse"):

    with st.spinner("Analyse en cours..."):

        # 🔹 CH4 GEE
        image = get_ch4_data(zone)

        # 🔹 CARBON MAPPER
        carbon_data = get_carbon_mapper_data()

        # -------------------------------
        # 🗺️ CARTE
        # -------------------------------
        Map = geemap.Map(center=[33.2, 3.5], zoom=8)

        vis_params = {
            'min': 1750,
            'max': 2000,
            'palette': ['blue', 'green', 'yellow', 'red']
        }

        Map.addLayer(image, vis_params, "CH4 Concentration")

        # -------------------------------
        # 🔴 AJOUT PLUMES (si dispo)
        # -------------------------------
        if carbon_data and "features" in carbon_data:

            for plume in carbon_data["features"][:50]:  # limiter pour performance
                coords = plume["geometry"]["coordinates"]

                folium.CircleMarker(
                    location=[coords[1], coords[0]],
                    radius=5,
                    color="red",
                    fill=True
                ).add_to(Map)

        # sauvegarde dans session
        st.session_state.map = Map
        st.session_state.result = "Analyse terminée"

# -------------------------------
# 📊 AFFICHAGE
# -------------------------------
if st.session_state.map:
    st.success(st.session_state.result)
    st.session_state.map.to_streamlit(height=600)

else:
    st.info("Clique sur 'Lancer l'analyse' pour commencer.")
