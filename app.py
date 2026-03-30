# ================= app.py — VERSION FINALE PROPRE =================

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
import requests
from tensorflow.keras.models import load_model
import folium
from streamlit_folium import st_folium
# ================= ZONES =================
zone_centre = [
    [32.7566, 3.3769],
    [32.7566, 3.6115],
    [33.0134, 3.6063],
    [33.0240, 2.9338],
    [32.8939, 2.9275],
    [32.8895, 3.3769]
]

zone_sud = [
    [32.4509, 2.8856],
    [32.4509, 3.3796],
    [32.8837, 3.3796],
    [32.8837, 2.8856]
]

zone_nord = [
    [33.0135, 3.1851],
    [33.2829, 3.1848],
    [33.2785, 3.8109],
    [33.0135, 3.8107]
]

from shapely.geometry import Point, Polygon

def is_inside_zone(lat, lon, zone_coords):
    poly = Polygon([(lon, lat) for lat, lon in zone_coords])
    point = Point(lon, lat)
    return poly.contains(point)
# ================= LOAD MODEL =================
MODEL_PATH = "AI_model/cnn_model.h5"

try:
    cnn_model = load_model(MODEL_PATH)
except:
    cnn_model = None

st.write("Modèle chargé :", cnn_model is not None)

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

# ================= CARBON MAPPER =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")
if not CARBON_API_TOKEN:
    st.error("❌ Token Carbon Mapper manquant")

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INPUT =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")
zone_choice = st.selectbox(
    "Choisir la zone",
    ["Centre", "Sud", "Nord"]
)
zone_map = {
    "Centre": zone_centre,
    "Sud": zone_sud,
    "Nord": zone_nord
}

selected_zone = zone_map[zone_choice]
# ================= PATHS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"

# ================= GEE FUNCTION =================
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

    images = collection.toList(size)

    for i in range(size):
        img = ee.Image(images.get(i))
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
            v = None

        if v is None:
            continue

        ch4_ppb = float(v)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today

        return ch4_ppb, date_img, no_pass_today

    return None, None, True

# ================= CARBON FUNCTION =================
def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"
    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {"gas": "CH4", "limit": 20,
              "bbox": f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
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

# ================= SECTION C : Carte CH₄ moyenne =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")

year_mean = st.selectbox(
    "Choisir l'année pour la carte",
    [2020, 2021, 2022, 2023, 2024, 2025]
)

if st.button("Afficher carte CH₄ moyenne"):

    mean_path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"

    if os.path.exists(mean_path):

        with rasterio.open(mean_path) as src:
            img = src.read(1)

        # Nettoyage des valeurs
        img[img <= 0] = np.nan

        # ================= AFFICHAGE PRO =================
        fig, ax = plt.subplots(figsize=(6,5))

        im = ax.imshow(img, cmap="viridis")

        # Barre de couleur (IMPORTANT pour PFE)
        plt.colorbar(im, ax=ax, label="CH₄ (ppb)")

        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")

        st.pyplot(fig)

    else:
        st.warning("Carte CH₄ introuvable")
# ================= SECTION D =================
st.markdown("## 🔎 Analyse annuelle")
if st.button("Analyser année"):
    if os.path.exists(csv_annual):
        df = pd.read_csv(csv_annual)
        st.dataframe(df)

# ================= SECTION E =================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE + IA + Zone)")

if st.button("Analyser CH₄ du jour"):

    st.info("Analyse en cours...")

    ch4, date_img, _ = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite")
        st.stop()

    # ================= IA =================
    if cnn_model is not None:
        image = np.full((64,64), ch4) / 3000.0
        image = image.reshape(1,64,64,1)
        prediction = cnn_model.predict(image)[0][0]
    else:
        prediction = None

    # ================= HISTORIQUE =================
    ch4_mean = None
    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)
        for col in ["CH4","ch4","mean"]:
            if col in df_hist.columns:
                ch4_mean = df_hist[col].mean()
                break

    # ================= AFFICHAGE =================
    st.success(f"📅 Date : {date_img}")
    st.success(f"🛰️ CH₄ : {ch4:.1f} ppb")

    if ch4_mean:
        st.info(f"📊 Moyenne : {ch4_mean:.1f} ppb")

    if prediction is not None:
        st.write(f"🧠 IA score : {prediction:.2f}")

    # ================= ZONE =================
    fuite_zone = False
    if prediction and prediction > 0.5:
        fuite_zone = is_inside_zone(latitude, longitude, selected_zone)

        if fuite_zone:
            st.error(f"🚨 Fuite DANS zone {zone_choice}")
        else:
            st.warning(f"⚠️ Fuite HORS zone {zone_choice}")

    # ================= DECISION =================
    if prediction:
        if prediction > 0.7:
            risk = "Critique"
        elif prediction > 0.5:
            risk = "Élevé"
        else:
            risk = "Normal"
    else:
        if ch4 >= 1900:
            risk = "Critique"
        elif ch4 >= 1850:
            risk = "Élevé"
        else:
            risk = "Normal"

    # ================= CARBON =================
    plumes = []
    if prediction and prediction > 0.5:
        plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

        if plumes:
            st.error(f"🔥 {len(plumes)} plume(s)")
        else:
            st.warning("Aucune plume détectée")

    # ================= TABLE =================
    df = pd.DataFrame([{
        "Date": date_img,
        "CH4": ch4,
        "Moyenne": ch4_mean,
        "Zone": zone_choice,
        "Risque": risk
    }])

    st.table(df)

    # ================= SAVE =================
    st.session_state["ch4"] = ch4
    st.session_state["plumes"] = plumes
    st.session_state["action"] = risk
# ================= SECTION G =================
st.markdown("## 🌍 Carte interactive CH₄")

if st.button("Afficher carte"):

    m = folium.Map(location=[latitude, longitude], zoom_start=6)

    # Satellite
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri"
    ).add_to(m)

    # Zones
    folium.Polygon(zone_centre, color="red", fill=True).add_to(m)
    folium.Polygon(zone_sud, color="green", fill=True).add_to(m)
    folium.Polygon(zone_nord, color="blue", fill=True).add_to(m)

    # Site
    folium.Marker([latitude, longitude]).add_to(m)

    # CH4
    heat = []

    if "ch4" in st.session_state:
        heat.append([latitude, longitude, st.session_state["ch4"]])

    # Plumes
    coords = []
    if "plumes" in st.session_state:
        for p in st.session_state["plumes"]:
            coords.append([p["lat"], p["lon"]])
            heat.append([p["lat"], p["lon"], p["emission"]])
            folium.Marker([p["lat"], p["lon"]]).add_to(m)

    # Heatmap
    if heat:
        from folium.plugins import HeatMap
        HeatMap(heat).add_to(m)

    # Zoom auto
    if coords:
        m.fit_bounds(coords)

    st_folium(m, width=750, height=500)
