# ================= app.py — VERSION FINALE CORRIGÉE =================

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import ee
import json
import tempfile
import folium
from streamlit_folium import st_folium
from datetime import datetime
# ================= INIT GEE =================
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

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= ZONES FIXES =================
zoneCentre = ee.Geometry.Polygon([
  [3.37696562, 32.75662617],
  [3.61159117, 32.75663435],
  [3.60634757, 33.01349055],
  [2.93385218, 33.02401464],
  [2.92757292, 32.89394392],
  [3.3769424, 32.88954646],
  [3.37696562, 32.75662617]
])

zoneSud = ee.Geometry.Polygon([
  [2.88567251, 32.45093128],
  [3.37963967, 32.45092697],
  [3.37964793, 32.88379946],
  [2.88561768, 32.88378899],
  [2.88567251, 32.45093128]
])

zoneNord = ee.Geometry.Polygon([
  [3.18513508, 33.01358581],
  [3.18482285, 33.28297225],
  [3.81093387, 33.27857017],
  [3.81077745, 33.01358819],
  [3.18513508, 33.01358581]
])

# ================= PATHS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"

# ================= SECTION A =================
st.markdown("## 📁 Section A — Données")
if st.button("Afficher dossiers"):
    for root, dirs, files in os.walk(DATA_DIR):
        st.write(root)
        for f in files:
            st.write(" └─", f)

# ================= SECTION B =================
st.markdown("## 📑 Section B — CSV")
if st.button("Afficher CSV"):
    if os.path.exists(csv_hist):
        df = pd.read_csv(csv_hist)
        st.dataframe(df.head())
    else:
        st.warning("CSV introuvable")

# ================= SECTION C =================
st.markdown("## 🗺️ Carte CH₄ moyenne")

year_mean = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])

if st.button("Afficher carte CH₄ moyenne"):

    path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"

    if os.path.exists(path):
        with rasterio.open(path) as src:
            img = src.read(1)

        img[img <= 0] = np.nan

        fig, ax = plt.subplots()
        im = ax.imshow(img, cmap="viridis")
        plt.colorbar(im, ax=ax, label="CH₄ (ppb)")
        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")

        st.pyplot(fig)
    else:
        st.warning("Carte introuvable")

# ================= SECTION D =================
st.markdown("## 🔎 Analyse annuelle")
if st.button("Analyser année"):
    if os.path.exists(csv_annual):
        df = pd.read_csv(csv_annual)
        st.dataframe(df)

# ================= SECTION E : ANALYSE DU JOUR + CARTE DYNAMIQUE =================
st.markdown("## 🔍 Analyse CH₄ du jour – Zone fixe Hassi R’Mel")

# Rayon de la zone autour du site
radius_km = 10  # tu peux ajuster
zone_site = ee.Geometry.Point([3.30, 32.93]).buffer(radius_km * 1000)

if st.button("Analyser CH₄ du jour"):

    st.info("Analyse en cours... ⏳")

    # ================= GEE : dernière image =================
    end = ee.Date(datetime.utcnow())
    start = end.advance(-60, "day")  # 60 derniers jours pour trouver image récente

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(zone_site)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    if collection.size().getInfo() == 0:
        st.error("⚠️ Aucune image satellite récente disponible")
        st.stop()

    latest_image = collection.first()

    # Récupérer la date réelle de l'image
    date_img = ee.Date(latest_image.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    # Moyenne CH₄ sur la zone
    ch4_val = latest_image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=zone_site,
        scale=1000,  # résolution plus fine pour correspondre à GEE
        maxPixels=1e9
    ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

    st.success(f"📅 Date image satellite : {date_img}")
    st.success(f"🛰️ CH₄ (GEE) : {ch4_val:.1f} ppb")

    # ================= ANOMALIE =================
    # Seuils simples
    if ch4_val >= 1900:
        risk = "Critique"
        action = "Intervention HSE urgente"
        st.error(f"⚠️ Niveau CH₄ critique : {ch4_val:.1f} ppb !")
    elif ch4_val >= 1850:
        risk = "Élevé"
        action = "Inspection recommandée"
        st.warning(f"⚠️ Niveau CH₄ élevé : {ch4_val:.1f} ppb")
    else:
        risk = "Normal"
        action = "Surveillance continue"
        st.success(f"✅ Niveau CH₄ normal : {ch4_val:.1f} ppb")

    # ================= CARBON MAPPER =================
    plumes = get_ch4_plumes_carbonmapper(32.93, 3.30)
    if len(plumes) > 0:
        st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
        for plume in plumes:
            st.write(f"- {plume['emission']} kg/h à ({plume['lat']:.4f}, {plume['lon']:.4f})")
    else:
        st.info("Aucune plume détectée par Carbon Mapper")

    # ================= TABLEAU =================
    df_day = pd.DataFrame([{
        "Date satellite": date_img,
        "Site": "Hassi R'mel",
        "Latitude": 32.93,
        "Longitude": 3.30,
        "CH₄ (ppb)": round(ch4_val, 2),
        "Risque": risk,
        "Action HSE": action
    }])
    st.table(df_day)

    # ================= CARTE DYNAMIQUE =================
    from folium.plugins import HeatMap

    m = folium.Map(location=[32.93, 3.30], zoom_start=8, tiles=None)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        overlay=False,
        control=True
    ).add_to(m)
    folium.TileLayer("OpenStreetMap", name="Carte").add_to(m)

    # Cercle site + couleur selon risque
    if ch4_val >= 1900:
        color = "red"
    elif ch4_val >= 1850:
        color = "orange"
    else:
        color = "green"

    folium.Circle(
        location=[32.93, 3.30],
        radius=radius_km*1000,
        color=color,
        fill=True,
        fill_opacity=0.4,
        popup=f"CH₄: {ch4_val:.1f} ppb"
    ).add_to(m)

    # Heatmap plumes
    heat_data = [[32.93, 3.30, ch4_val]]
    for plume in plumes:
        heat_data.append([plume["lat"], plume["lon"], plume["emission"]])
        folium.Marker(
            [plume["lat"], plume["lon"]],
            popup=f"🔥 Plume: {plume['emission']} kg/h",
            icon=folium.Icon(color="red", icon="cloud")
        ).add_to(m)

    HeatMap(heat_data, radius=25).add_to(m)
    folium.LayerControl().add_to(m)
    st_folium(m, width=750, height=550)
