# ================= app.py — FINAL CLEAN VERSION =================

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import ee
import json
import tempfile
from datetime import datetime, timedelta
import io

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


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
st.set_page_config(page_title="CH₄ Monitoring", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")


# ================= IA SIMPLE =================
def detect_ch4_anomaly(image_array):
    val = np.nanmean(image_array)

    if np.isnan(val):
        return "❌ Pas de données", 0.0
    elif val > 1920:
        return "🔥 Fuite critique", 1.0
    elif val > 1880:
        return "⚠️ Suspect", 0.7
    else:
        return "✅ Normal", 0.1


# ================= ZONES =================
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


# ================= CARBON MAPPER (FINAL SIMPLE VERSION) =================
import streamlit.components.v1 as components

st.markdown("## 🛰️ Carbon Mapper — Methane Emissions (Live)")

st.info("Affichage de la plateforme officielle Carbon Mapper (données satellites haute résolution).")

components.iframe(
    "https://data.carbonmapper.org/",
    height=750,
    scrolling=True
)


# ================= ANALYSIS SECTION =================
st.markdown("## 📊 Analyse CH₄ (Sentinel-5P)")

year = st.selectbox("Année", [2020, 2021, 2022, 2023, 2024, 2025])

if st.button("Analyser CH₄"):
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
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val = value.getInfo()
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


# ================= RECENT ANALYSIS =================
st.markdown("## 🔎 Analyse récente (7 jours)")

if st.button("Lancer analyse récente"):
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
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        try:
            val = value.getInfo()
        except:
            val = None

        status, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))

        results.append({
            "Zone": name,
            "CH₄": round(val, 2) if val else "N/A",
            "Statut": status,
            "Score IA": score
        })

    df = pd.DataFrame(results)
    st.dataframe(df)
    st.bar_chart(df.set_index("Zone"))


# ================= POINT ANALYSIS =================
st.markdown("## 🎯 Analyse point")

lat = st.number_input("Latitude", value=32.90)
lon = st.number_input("Longitude", value=3.30)

if st.button("Analyser point"):
    today = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = today.advance(-7, "day")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterDate(start, today)
        .select("CH4_column_volume_mixing_ratio_dry_air")
    )

    image = collection.mean()
    point = ee.Geometry.Point([lon, lat])

    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    try:
        val = value.getInfo()
    except:
        val = None

    status, score = detect_ch4_anomaly(np.array([[val]]) if val else np.array([[np.nan]]))

    if val:
        st.success(f"CH₄: {round(val,2)} ppb | {status} | Score {score}")
    else:
        st.error("Pas de donnée")
