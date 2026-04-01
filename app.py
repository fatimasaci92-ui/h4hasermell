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
    maxPixels=1e9,
    bestEffort=True
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
st.markdown("## 📡 Analyse CH₄ récente par zone (version fiable)")

if st.button("Analyser CH₄ (derniers jours)"):
    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")   # 7 derniers jours

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    def compute(zone, name):
        size = collection.size().getInfo()
        if size == 0:
            return {"Zone": name, "CH₄ (ppb)": None}

        image = collection.mean()
        for i in range(size):
            img = ee.Image(images.get(i))
           value = img.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=zone,
    scale=7000,
    maxPixels=1e9,
    bestEffort=True
).get("CH4_column_volume_mixing_ratio_dry_air")

            try:
                val = value.getInfo()
            except:
                val = None

            if val is not None:
                return {"Zone": name, "CH₄ (ppb)": round(val, 2)}

        return {"Zone": name, "CH₄ (ppb)": None}

    results = [
        compute(zoneCentre, "Centre"),
        compute(zoneSud, "Sud"),
        compute(zoneNord, "Nord")
    ]

    df = pd.DataFrame(results)

    # 🔥 Détection automatique des anomalies
    def detect_anomaly(value):
        if value is None:
            return "Pas de données"
        elif value > 1900:
            return "🔴 Critique"
        elif value > 1850:
            return "🟠 Élevé"
        else:
            return "🟢 Normal"

    df["Risque"] = df["CH₄ (ppb)"].apply(detect_anomaly)

    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))
# ================= SECTION G PRO =================
st.markdown("## 🌍 Carte CH₄ PRO (GEE + Zones + Plumes)")

# 🔥 Etat persistant
if "map_ready" not in st.session_state:
    st.session_state["map_ready"] = False

if st.button("Afficher carte PRO"):
    st.session_state["map_ready"] = True

# ================= AFFICHAGE =================
if st.session_state["map_ready"]:

    st.info("🛰️ Chargement des données satellites...")

    site_lat = 32.90
    site_lon = 3.30

    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    # ================= IMAGE GEE =================
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

image = collection.mean()
    # ❌ Sécurité
    if image is None:
        st.error("❌ Aucune image satellite disponible")
        st.stop()

    # ================= MAP =================
    m = folium.Map(location=[site_lat, site_lon], zoom_start=7, tiles=None)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite"
    ).add_to(m)

    folium.TileLayer("OpenStreetMap", name="Carte").add_to(m)

    # ================= COUCHE CH4 =================
    map_id = image.getMapId({
        "min": 1800,
        "max": 2000,
        "palette": ["blue", "green", "yellow", "red"]
    })

    folium.TileLayer(
        tiles=map_id["tile_fetcher"].url_format,
        attr="CH4",
        name="CH₄",
        overlay=True,
        opacity=0.6
    ).add_to(m)

    # ================= IA SIMPLE =================
    def detect_leak(val):
        if val is None:
            return "❌ No data", "gray"
        elif val > 1920:
            return "🔥 Fuite", "red"
        elif val > 1880:
            return "⚠️ Suspect", "orange"
        else:
            return "✅ Normal", "green"

    # ================= ZONES =================
    zones = [
        ("Centre", zoneCentre),
        ("Sud", zoneSud),
        ("Nord", zoneNord)
    ]

    results = []
    all_coords = []

    for name, zone in zones:

        value = image.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=zone,
    scale=7000,
    maxPixels=1e9,
    bestEffort=True
).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val = value.getInfo()
        except:
            val = None

        status, color = detect_leak(val)
        val_str = f"{round(val,2)} ppb" if val else "No data"

        results.append({
            "Zone": name,
            "CH₄": val_str,
            "Statut": status
        })

        # 🔥 coordonnées corrigées
       coords = zone.coordinates().getInfo()[0]
       coords = [[lat, lon] for lon, lat in coords]
        all_coords.extend(coords)

        folium.Polygon(
            locations=coords,
            color=color,
            fill=True,
            fill_opacity=0.4,
            popup=f"<b>{name}</b><br>CH₄: {val_str}<br>{status}"
        ).add_to(m)

    # ================= SCAN AUTOMATIQUE =================
    st.markdown("### 🔍 Scan automatique")

    if st.button("Lancer scan intelligent"):

        image_mean = collection.mean()

        lat_range = np.linspace(32.5, 33.2, 8)
        lon_range = np.linspace(2.8, 3.8, 8)

        for lat in lat_range:
            for lon in lon_range:

                point = ee.Geometry.Point([lon, lat])

               value = image_mean.reduceRegion(
    reducer=ee.Reducer.mean(),
    geometry=point,
    scale=10000,
    maxPixels=1e9,
    bestEffort=True
).get("CH4_column_volume_mixing_ratio_dry_air")

                try:
                    val = value.getInfo()
                except:
                    val = None

                if val is None:
                    continue

                if val > 1920:
                    color = "red"
                    status = "🔥 Critique"
                elif val > 1880:
                    color = "orange"
                    status = "⚠️ Suspect"
                else:
                    continue

                folium.CircleMarker(
                    [lat, lon],
                    radius=8,
                    color=color,
                    fill=True,
                    fill_opacity=0.9,
                    popup=f"{status} - {round(val,2)} ppb"
                ).add_to(m)

                all_coords.append([lat, lon])

    # ================= PLUMES =================
    token = st.secrets.get("CARBON_API_TOKEN", "")

    if token:
        try:
            import requests

            r = requests.get(
                "https://api.carbonmapper.org/api/v1/catalog/plumes",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "gas": "CH4",
                    "limit": 20,
                    "bbox": f"{site_lon-1},{site_lat-1},{site_lon+1},{site_lat+1}"
                }
            )

            if r.status_code == 200:
                data = r.json()

                for f in data.get("features", []):
                    lon, lat = f["geometry"]["coordinates"]
                    emission = f["properties"].get("emission_rate", 0)

                    folium.CircleMarker(
                        [lat, lon],
                        radius=8,
                        color="red",
                        fill=True,
                        fill_opacity=0.8,
                        popup=f"🔥 Plume<br>{emission} kg/h"
                    ).add_to(m)

                    all_coords.append([lat, lon])

        except:
            st.warning("⚠️ Carbon Mapper indisponible")

    # ================= SITE =================
    folium.Marker(
        [site_lat, site_lon],
        popup="📍 Hassi R'mel",
        icon=folium.Icon(color="blue")
    ).add_to(m)

    # ================= ZOOM AUTO =================
    if len(all_coords) > 0:
        m.fit_bounds(all_coords)

    folium.LayerControl().add_to(m)

    # ================= AFFICHAGE =================
    st_folium(m, width=750, height=550)

    # ================= TABLE =================
    st.markdown("## 📊 Résultats Analyse")
    st.dataframe(pd.DataFrame(results))
# ================= SECTION H =================
st.markdown("## 🎯 Détection locale (point précis)")

lat_point = st.number_input("Latitude point", value=32.90)
lon_point = st.number_input("Longitude point", value=3.30)

if st.button("Analyser ce point"):

    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )

    image = collection.mean()

    point = ee.Geometry.Point([lon_point, lat_point])

    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000,
        maxPixels=1e9,
        bestEffort=True
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    try:
        val = value.getInfo()
    except:
        val = None

    def detect(val):
        if val is None or val == 0:
            return "❌ Pas de donnée", "gray"
        elif val > 1920:
            return "🔥 Fuite critique", "red"
        elif val > 1880:
            return "⚠️ Suspicion", "orange"
        else:
            return "✅ Normal", "green"

    status, color = detect(val)

    if val:
        st.success(f"CH₄ : {round(val,2)} ppb")
    else:
        st.error("Pas de valeur")

    st.write(f"Statut : {status}")

    st.write(f"Statut : {status}")
