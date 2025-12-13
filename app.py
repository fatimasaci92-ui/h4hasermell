# app.py — VERSION COMPLÈTE CORRIGÉE

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import ee
import json
import tempfile

# ================= INITIALISATION GOOGLE EARTH ENGINE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"],
        key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= FONCTION GEE CORRIGÉE =================
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

        ch4_ppb = float(v) * 1e9
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today

        return ch4_ppb, date_img, no_pass_today

    return None, None, True

# ================= ANALYSE CH₄ DU JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour (Google Earth Engine)")

if st.button("Analyser CH₄ du jour"):
    st.info("Analyse en cours...")

    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible sur la période analysée.")
        st.stop()

    if no_pass_today:
        st.error("☁️ Pas de passage satellite aujourd’hui (nuages ou orbite)")
        st.warning(f"➡️ Dernière image disponible sur GEE : **{date_img}**")

    st.success(f"CH₄ : **{ch4:.1f} ppb** (image du {date_img})")

    # Analyse HSE
    if ch4 >= 1900:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
        action = "Alerter, sécuriser la zone et stopper opérations"
    else:
        st.success("CH₄ normal")
        action = "Surveillance continue"

    df = pd.DataFrame([{
        "Date image": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ (ppb)": round(ch4, 2),
        "Anomalie": "Oui" if ch4 >= 1900 else "Non",
        "Action HSE": action
    }])

    st.table(df)

# ================= FIN =================
