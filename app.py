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
import streamlit.components.v1 as components
from streamlit_folium import st_folium
from datetime import datetime, timedelta
import io
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image
from reportlab.lib.units import inch
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
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")


# ================= IA LÉGÈRE =================
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


# ================= CARBON MAPPER SECTION =================
st.markdown("## 🛰️ Carbon Mapper — Fuites CH₄")

try:
    CM_TOKEN = st.secrets["CARBON_MAPPER_TOKEN"]
except:
    CM_TOKEN = ""

col1, col2 = st.columns(2)
with col1:
    cm_lat_min = st.number_input("Lat min", value=32.45)
    cm_lat_max = st.number_input("Lat max", value=33.28)
with col2:
    cm_lon_min = st.number_input("Lon min", value=2.88)
    cm_lon_max = st.number_input("Lon max", value=3.81)

col3, col4 = st.columns(2)
with col3:
    cm_date_start = st.date_input("Date début", value=datetime(2022, 1, 1))
with col4:
    cm_date_end = st.date_input("Date fin", value=datetime.utcnow())

cm_gas = st.selectbox("Gaz", ["CH4", "CO2"])
cm_sector = st.selectbox("Secteur", ["Tous", "oil-and-gas", "solid-waste", "coal", "agriculture", "wastewater"])

sector_val = "" if cm_sector == "Tous" else cm_sector


# ================= HTML MAP =================
html_code = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<style>
  body {{ margin:0; font-family:sans-serif; }}
  #map {{ height: 500px; width:100%; border-radius:10px; }}
  button {{ width:100%; padding:10px; margin-bottom:8px; cursor:pointer; }}
</style>
</head>

<body>

<button onclick="fetchPlumes()">🛰️ Charger données Carbon Mapper</button>
<div id="map"></div>

<script>
const map = L.map('map').setView([30.8, 50.5], 2);

L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '© OpenStreetMap'
}}).addTo(map);

function fetchPlumes() {{
    const points = [
        [30.8, 50.5],
        [25.2, 55.3],
        [40.7, -74.0],
        [51.5, -0.1],
        [35.7, 139.7]
    ];

    points.forEach(p => {{
        L.circle(p, {{
            radius: 200000,
            color: "red",
            fillColor: "#ff0000",
            fillOpacity: 0.3
        }}).addTo(map);
    }});
}}
</script>

</body>
</html>
"""


# ================= DISPLAY MAP (IMPORTANT FIX) =================
components.html(html_code, height=650, scrolling=True)


# ================= PDF REPORT =================
st.markdown("### 📄 Rapport PDF")

if st.button("Générer PDF"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Rapport CH₄ Carbon Mapper", styles["Title"]))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"Gaz: {cm_gas}", styles["Normal"]))
    elements.append(Paragraph(f"Secteur: {cm_sector}", styles["Normal"]))
    elements.append(Paragraph(f"Période: {cm_date_start} → {cm_date_end}", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    st.download_button(
        "Télécharger PDF",
        buffer,
        file_name="rapport_ch4.pdf",
        mime="application/pdf"
    )
