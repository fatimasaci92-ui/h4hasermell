# ================= IMPORTS =================
import streamlit as st
import pandas as pd
import numpy as np
import folium
import streamlit.components.v1 as components
import requests
import io
import base64
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# ================= CONFIG =================
st.set_page_config(page_title="CH₄ Carbon Mapper", layout="wide")
st.title("🛰️ Surveillance CH₄ — Carbon Mapper (HSE)")

# ================= TOKEN =================
CM_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")

if not CM_TOKEN:
    st.error("❌ Ajoute CARBON_API_TOKEN dans secrets.toml")
    st.stop()

# ================= INPUTS =================
col1, col2 = st.columns(2)

with col1:
    lat_min = st.number_input("Lat min", value=32.45)
    lat_max = st.number_input("Lat max", value=33.28)

with col2:
    lon_min = st.number_input("Lon min", value=2.88)
    lon_max = st.number_input("Lon max", value=3.81)

col3, col4 = st.columns(2)

with col3:
    date_start = st.date_input("Date début", value=datetime(2022, 1, 1))

with col4:
    date_end = st.date_input("Date fin", value=datetime.utcnow())

gas = st.selectbox("Gaz", ["CH4", "CO2"])

bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"

# ================= API =================
API_URL = "https://api.carbonmapper.org/api/v1/catalog/plumes/annotated"

# ================= FUNCTION =================
def get_data():
    headers = {"Authorization": f"Bearer {CM_TOKEN}"}

    params = {
        "limit": 200,
        "gas": gas,
        "bbox": bbox,
        "datetime": f"{date_start}T00:00:00Z/{date_end}T23:59:59Z"
    }

    r = requests.get(API_URL, headers=headers, params=params)

    if r.status_code != 200:
        st.error(f"❌ Erreur API {r.status_code}")
        return []

    data = r.json()
    return data.get("items", [])

# ================= ANALYSE =================
def analyze_emission(val):
    if val is None:
        return "❌ N/A", 0

    if val > 1000:
        return "🔥 Fuite critique", 1.0
    elif val > 300:
        return "⚠️ Suspect", 0.6
    else:
        return "✅ Normal", 0.2

# ================= RUN =================
if st.button("🔍 Lancer analyse Carbon Mapper"):

    items = get_data()

    if not items:
        st.warning("⚠️ Aucun panache détecté")
        st.stop()

    st.success(f"✅ {len(items)} fuites détectées")

    results = []
    points = []

    for p in items:

        prop = p.get("properties", p)

        lat = prop.get("source_lat") or prop.get("lat")
        lon = prop.get("source_lon") or prop.get("lon")

        emission = prop.get("emission_auto") or prop.get("emission")

        status, score = analyze_emission(emission)

        if lat and lon:
            points.append([lat, lon, emission, status])

        results.append({
            "Latitude": lat,
            "Longitude": lon,
            "Débit (kg/h)": emission,
            "Statut": status,
            "Score": score
        })

    df = pd.DataFrame(results)
    st.dataframe(df)

    # ================= MAP =================
    center = [np.mean([p[0] for p in points]), np.mean([p[1] for p in points])]

    m = folium.Map(location=center, zoom_start=8)

    for p in points:

        lat, lon, emission, status = p

        color = "green"
        if status == "🔥 Fuite critique":
            color = "red"
        elif status == "⚠️ Suspect":
            color = "orange"

        folium.CircleMarker(
            location=[lat, lon],
            radius=8,
            color=color,
            fill=True,
            popup=f"Débit: {emission} kg/h"
        ).add_to(m)

    st.write("🗺️ Carte des fuites")
    components.html(m._repr_html_(), height=500)

    # ================= PDF =================
    if st.button("📄 Générer rapport PDF"):

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()

        elements = []

        elements.append(Paragraph("📊 Rapport CH₄ — Carbon Mapper", styles["Title"]))
        elements.append(Spacer(1, 10))

        elements.append(Paragraph(f"Date: {datetime.utcnow()}", styles["Normal"]))
        elements.append(Paragraph(f"Zone: {bbox}", styles["Normal"]))
        elements.append(Spacer(1, 10))

        table_data = [["Lat", "Lon", "Débit", "Statut"]]

        for r in results:
            table_data.append([
                str(r["Latitude"]),
                str(r["Longitude"]),
                str(r["Débit (kg/h)"]),
                r["Statut"]
            ])

        table = Table(table_data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.grey),
            ("TEXTCOLOR", (0,0), (-1,0), colors.white),
            ("GRID", (0,0), (-1,-1), 0.5, colors.black)
        ]))

        elements.append(table)

        doc.build(elements)
        buffer.seek(0)

        st.download_button(
            "📥 Télécharger PDF",
            buffer,
            file_name="CH4_CarbonMapper_report.pdf"
        )
