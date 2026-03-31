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

# ================= SECTION E =================
st.markdown("## 📊 Analyse CH₄ par Zone et Année")

year = st.selectbox("Choisir année analyse", [2020, 2021, 2022, 2023, 2024, 2025])

if st.button("Lancer analyse CH₄"):

    start = ee.Date(f"{year}-01-01")
    end = ee.Date(f"{year}-12-31")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )

    def compute(zone, name):
        val = collection.mean().reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zone,
            scale=7000,
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val = val.getInfo()
        except:
            val = None

        return {"Zone": name, "CH₄ (ppb)": val}

    results = [
        compute(zoneCentre, "Centre"),
        compute(zoneSud, "Sud"),
        compute(zoneNord, "Nord")
    ]

    df = pd.DataFrame(results)

    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))
# ================= SECTION F =================
st.markdown("## 📡 Analyse CH₄ récente par zone (avec date réelle)")

if st.button("Analyser CH₄ (derniers jours)"):

    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    def compute(zone, name):

        size = collection.size().getInfo()

        if size == 0:
            return {"Zone": name, "CH₄": "Pas de données", "Date": "-"}

        images = collection.toList(size)

        for i in range(size):

            img = ee.Image(images.get(i))

            value = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone,
                scale=7000,
                maxPixels=1e9
            ).get("CH4_column_volume_mixing_ratio_dry_air")

            date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd")

            try:
                val = value.getInfo()
                date_val = date_img.getInfo()
            except:
                val = None

            if val is not None:
                return {
                    "Zone": name,
                    "CH₄ (ppb)": round(val, 2),
                    "Date image": date_val
                }

        return {"Zone": name, "CH₄": "Aucune donnée", "Date": "-"}

    results = [
        compute(zoneCentre, "Centre"),
        compute(zoneSud, "Sud"),
        compute(zoneNord, "Nord")
    ]

    df = pd.DataFrame(results)

    st.dataframe(df)
    st.bar_chart(df.set_index("Zone")[["CH₄ (ppb)"]])
# ================= SECTION G =================
st.markdown("## 🌍 Carte des zones")

if st.button("Afficher carte zones"):

    center = zoneCentre.centroid().coordinates().getInfo()[::-1]

    m = folium.Map(location=center, zoom_start=7)

    def add_zone(zone, name, color):
        coords = zone.coordinates().getInfo()[0]
        coords = [[c[1], c[0]] for c in coords]

        folium.Polygon(
            locations=coords,
            color=color,
            fill=True,
            fill_opacity=0.3,
            popup=name
        ).add_to(m)

    add_zone(zoneCentre, "Centre", "red")
    add_zone(zoneSud, "Sud", "green")
    add_zone(zoneNord, "Nord", "blue")

    st_folium(m, width=750, height=550)
    # ================= SECTION H =================
st.markdown("## 🌍 Carte CH₄ dynamique (GEE)")

if st.button("Afficher carte CH₄ réelle"):

    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    image = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
        .first()
    )

    vis_params = {
        "min": 1800,
        "max": 2000,
        "palette": ["blue", "green", "yellow", "red"]
    }

    map_center = zoneCentre.centroid().coordinates().getInfo()[::-1]

    m = folium.Map(location=map_center, zoom_start=6)

    map_id = ee.Image(image).getMapId(vis_params)

    folium.TileLayer(
        tiles=map_id["tile_fetcher"].url_format,
        attr="Google Earth Engine",
        name="CH4",
        overlay=True,
        control=True
    ).add_to(m)

    folium.LayerControl().add_to(m)

    st_folium(m, width=750, height=500)
