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

        images = collection.toList(size)
        for i in range(size):
            img = ee.Image(images.get(i))
            value = img.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone,
                scale=7000,
                maxPixels=1e9
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
# ================= SECTION G =================
st.markdown("## 🌍 Carte CH₄ FIXE (GEE + Plumes + Zones)")

if st.button("Afficher carte CH₄ stable"):

    # ✅ COORDONNÉES FIXES (TRÈS IMPORTANT)
    site_lat = 32.90
    site_lon = 3.30

    # 🔥 Forcer zone visible (empêche la carte de partir ailleurs)
    bounds = [
        [32.4, 2.8],   # Sud-Ouest
        [33.3, 3.9]    # Nord-Est
    ]

    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    image = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
        .first()
    )

    if image is None:
        st.warning("⚠️ Pas d'image CH₄")
    else:

        vis_params = {
            "min": 1800,
            "max": 2000,
            "palette": ["blue", "green", "yellow", "red"]
        }

        # ✅ CARTE FIXE
        m = folium.Map(
            location=[site_lat, site_lon],
            zoom_start=8,
            max_bounds=True
        )

        # 🔒 BLOQUER LA CARTE DANS LA ZONE
        m.fit_bounds(bounds)

        # ================= GEE LAYER =================
        map_id = image.getMapId(vis_params)

        folium.TileLayer(
            tiles=map_id["tile_fetcher"].url_format,
            attr="GEE",
            name="CH4",
            overlay=True,
            control=True
        ).add_to(m)

        # ================= ZONES =================
        zones = [
            ("Centre", zoneCentre),
            ("Sud", zoneSud),
            ("Nord", zoneNord)
        ]

        def detect_risk(val):
            if val is None:
                return "N/A"
            elif val > 1900:
                return "🔴 Critique"
            elif val > 1850:
                return "🟠 Élevé"
            else:
                return "🟢 Normal"

        for name, zone in zones:

            mean = image.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=zone,
                scale=7000,
                maxPixels=1e9
            ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

            risk = detect_risk(mean)

            val_str = f"{round(mean,2)} ppb" if mean else "No data"

            coords = zone.coordinates().getInfo()[0]
            coords = [[lat, lon] for lon, lat in coords]

            folium.Polygon(
                locations=coords,
                color="red" if risk=="🔴 Critique" else ("orange" if risk=="🟠 Élevé" else "green"),
                fill=True,
                fill_opacity=0.3,
                popup=f"{name} | CH₄: {val_str} | {risk}"
            ).add_to(m)

        # ================= PLUMES =================
        import requests

        token = st.secrets.get("CARBON_API_TOKEN", "")

        if token:
            try:
                r = requests.get(
                    "https://api.carbonmapper.org/api/v1/catalog/plumes",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "gas": "CH4",
                        "limit": 20,
                        "bbox": f"{site_lon-0.5},{site_lat-0.5},{site_lon+0.5},{site_lat+0.5}"
                    }
                )

                if r.status_code == 200:
                    data = r.json()

                    for f in data.get("features", []):
                        lon, lat = f["geometry"]["coordinates"]
                        emission = f["properties"].get("emission_rate", 0)

                        folium.CircleMarker(
                            [lat, lon],
                            radius=6,
                            color="red",
                            fill=True,
                            popup=f"🔥 {emission} kg/h"
                        ).add_to(m)

            except:
                st.warning("Erreur Carbon Mapper")

        # ================= SITE =================
        folium.Marker(
            [site_lat, site_lon],
            popup="📍 Hassi R'mel",
            icon=folium.Icon(color="blue")
        ).add_to(m)

        folium.LayerControl().add_to(m)

        # ✅ AFFICHAGE STABLE
        st_folium(m, width=750, height=550)
