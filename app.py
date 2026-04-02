# ================= app.py — VERSION FINALE AVEC IA LÉGÈRE =================

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

# ================= IA LÉGÈRE (SANS TORCH) =================
def detect_ch4_anomaly(image_array):
    """IA simplifiée par seuils, compatible Streamlit Cloud"""
    val = np.nanmean(image_array)
    if np.isnan(val):
        return "❌ Pas de données", 0.0
    elif val > 1920:
        return "🔥 Fuite critique", 1.0
    elif val > 1880:
        return "⚠️ Suspect", 0.7
    else:
        return "✅ Normal", 0.1

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
        value = collection.mean().reduceRegion(
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
        return {"Zone": name, "CH₄ (ppb)": val}

    results = [compute(zoneCentre, "Centre"), compute(zoneSud, "Sud"), compute(zoneNord, "Nord")]
    df = pd.DataFrame(results)
    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))

# ================= SECTION F =================
st.markdown("## 📡 Analyse CH₄ récente par zone")
if st.button("Analyser CH₄ (derniers jours)"):
    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )
    image = collection.mean()
    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]
    results = []

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

        status_ia, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
        results.append({
            "Zone": name,
            "CH₄": round(val,2) if val else "No data",
            "Risque IA": status_ia,
            "Score IA": round(score,2)
        })

    df = pd.DataFrame(results)
    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))


# ================= SECTION G =================
st.markdown("## 🌍 Carte CH₄ PRO")
# Initialisation session_state
if "map" not in st.session_state:
    st.session_state.map = None

if st.button("Afficher carte PRO"):

    zones = [("Centre", zoneCentre), ("Sud", zoneSud), ("Nord", zoneNord)]

    # Calcul centre carte
    all_lats, all_lons = [], []
    for name, zone in zones:
        coords = zone.coordinates().getInfo()[0]
        for lon, lat in coords:
            all_lats.append(lat)
            all_lons.append(lon)

    center_lat = (max(all_lats) + min(all_lats)) / 2
    center_lon = (max(all_lons) + min(all_lons)) / 2
    sw = [min(all_lats), min(all_lons)]
    ne = [max(all_lats), max(all_lons)]

    # Création carte
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8)
    m.fit_bounds([sw, ne])

    # Charger données CH4
    from datetime import timedelta
    today = datetime.utcnow()
    start = today - timedelta(days=7)

    collection = ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4") \
        .filterDate(start, today) \
        .select("CH4_column_volume_mixing_ratio_dry_air")

    count = collection.size().getInfo()
    if count == 0:
        st.warning("⚠️ Aucune image disponible")
    else:
        image = collection.mean()

        # Vérification zone
        mean_val = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=zoneCentre,
            scale=7000,
            maxPixels=1e9,
            bestEffort=True
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val_check = mean_val.getInfo()
        except:
            val_check = None

        if val_check is None:
            st.warning("⚠️ Pas de données sur la zone")
        else:
            # Palette dynamique
            min_val = val_check * 0.95
            max_val = val_check * 1.05

            map_id = image.getMapId({
                "min": min_val,
                "max": max_val,
                "palette": ["blue", "green", "yellow", "red"]
            })

            folium.TileLayer(
                tiles=map_id["tile_fetcher"].url_format,
                attr="CH4",
                overlay=True
            ).add_to(m)

            # Dernière date satellite
            last_image = collection.sort('system:time_start', False).first()
            last_date = ee.Date(last_image.get('system:time_start')).format('YYYY-MM-dd').getInfo()

            results = []

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

                # IA
                status_ia, score = detect_ch4_anomaly(
                    np.array([[val]]) if val else np.array([[np.nan]])
                )

                color = "green"
                if status_ia == "🔥 Fuite critique":
                    color = "red"
                elif status_ia == "⚠️ Suspect":
                    color = "orange"

                coords = [[lat, lon] for lon, lat in zone.coordinates().getInfo()[0]]

                folium.Polygon(
                    locations=coords,
                    color=color,
                    fill=True,
                    fill_opacity=0.4,
                    tooltip=f"{name}: {status_ia} (Score {round(score,2)})"
                ).add_to(m)

                results.append({
                    "Zone": name,
                    "CH₄": val,
                    "Statut IA": status_ia,
                    "Score IA": round(score,2),
                    "Dernière date": last_date
                })

            # Sauvegarder carte
            st.session_state.map = m

            # Tableau résultats
            st.dataframe(pd.DataFrame(results))

# Affichage carte FIXE (hors bouton)
st_folium(
    st.session_state.map,
    width=700,
    height=500,
    scroll_wheel_zoom=False,
    key="map_ch4"
)
# ================= SECTION H =================
st.markdown("## 🎯 Détection locale")
lat_point = st.number_input("Latitude", value=32.90)
lon_point = st.number_input("Longitude", value=3.30)

if st.button("Analyser point"):
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

    status_ia, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))
    if val:
        st.success(f"CH₄ : {round(val,2)} ppb — IA: {status_ia} (Score {round(score,2)})")
    else:
        st.error("❌ Pas de donnée")
