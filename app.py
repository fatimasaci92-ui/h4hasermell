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

# ================= SECTION C =================
st.markdown("## 🗺️ Section C — Carte")
year_mean = st.selectbox("Année", [2020,2021,2022,2023,2024,2025])

if st.button("Afficher carte"):
    path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"
    if os.path.exists(path):
        with rasterio.open(path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        st.image(img, caption=f"CH₄ {year_mean}")
    else:
        st.warning("Carte introuvable")

# ================= SECTION D =================
st.markdown("## 🔎 Analyse annuelle")
if st.button("Analyser année"):
    if os.path.exists(csv_annual):
        df = pd.read_csv(csv_annual)
        st.dataframe(df)

# ================= SECTION E =================
st.markdown("## 🔍 Analyse CH₄ du jour")

if st.button("Analyser CH₄ du jour"):
    st.info("Analyse en cours...")

    ch4, date_img, _ = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("Pas de données")
        st.stop()

    # IA
    if cnn_model is not None:
        image = np.full((64,64), ch4) / 3000.0
        image = image.reshape(1,64,64,1)
        prediction = cnn_model.predict(image)[0][0]
    else:
        prediction = None

    st.success(f"CH₄ : {ch4:.1f} ppb")

    # DECISION
    if prediction is not None:
        st.write(f"Score IA : {prediction:.2f}")

        if prediction > 0.7:
            risk = "Critique (IA)"
            action = "Intervention urgente"
            st.error("Fuite détectée")
        elif prediction > 0.5:
            risk = "Élevé"
            action = "Inspection"
            st.warning("Suspicion fuite")
        else:
            risk = "Normal"
            action = "Surveillance"
            st.success("OK")

        if prediction > 0.5:
            plumes = get_ch4_plumes_carbonmapper(latitude, longitude)
            if len(plumes) > 0:
                st.error(f"{len(plumes)} plume(s) détectée(s)")

    else:
        if ch4 >= 1900:
            risk = "Critique"
            action = "Arrêt"
        elif ch4 >= 1850:
            risk = "Élevé"
            action = "Inspection"
        else:
            risk = "Normal"
            action = "Surveillance"

    # TABLE
    df = pd.DataFrame([{
        "CH4": ch4,
        "Risque": risk,
        "Action": action
    }])

    st.table(df)

# ================= PDF =================
def generate_pdf(site, date, ch4, action):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph("Rapport CH4", styles["Title"]))
    story.append(Paragraph(f"Site: {site}", styles["Normal"]))
    story.append(Paragraph(f"Date: {date}", styles["Normal"]))
    story.append(Paragraph(f"CH4: {ch4}", styles["Normal"]))
    story.append(Paragraph(f"Action: {action}", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer
