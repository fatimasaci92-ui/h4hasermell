# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import ee
import json
import tempfile
import os
from datetime import datetime
import folium
from streamlit_folium import st_folium
import plotly.express as px
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import smtplib
from email.mime.text import MIMEText

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")
st.info("⚠️ Surveillance satellitaire – ne remplace pas les inspections terrain.")

# ===================== GEE INIT =====================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"], key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ===================== SIDEBAR =====================
st.sidebar.header("📍 Paramètres du site")
sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}
selected_site = st.sidebar.selectbox("Site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORICAL DATA =====================
CSV_PATH = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(CSV_PATH)

def get_ch4_series(df):
    for c in df.columns:
        if "ch4" in c.lower():
            return df[c]
    raise ValueError("Colonne CH4 introuvable")

# ===================== SESSION STATE =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
    st.session_state.results = {}

# ===================== FUNCTIONS =====================
def get_latest_ch4(lat, lon, days_back=90):
    geom = ee.Geometry.Point([lon, lat]).buffer(3500)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    col = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )

    if col.size().getInfo() == 0:
        return None, None

    img = ee.Image(col.first())
    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    val = img.reduceRegion(
        ee.Reducer.mean(), geom, 7000, maxPixels=1e9
    ).get("CH4_column_volume_mixing_ratio_dry_air").getInfo()

    return (val * 1000 if val else None), date_img

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

def generate_hse_pdf(results):
    path = f"/tmp/Rapport_CH4_{results['site']}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph("Rapport HSE – Surveillance CH₄", styles["Title"]))
    elems.append(Spacer(1, 12))

    table = Table([
        ["Indicateur", "Valeur"],
        ["Site", results["site"]],
        ["CH₄ (ppb)", f"{results['ch4']:.1f}"],
        ["Z-score", f"{results['z']:.2f}"],
        ["Risque", results["risk"]],
        ["Action", results["decision"]],
    ])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightblue),
    ]))

    elems.append(table)
    doc.build(elems)
    return path

# ===================== ANALYSIS =====================
if st.button("🚀 Lancer l’analyse"):
    series = get_ch4_series(df_hist)
    ch4, date_img = get_latest_ch4(lat_site, lon_site)

    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "CSV"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk, decision, color = "Critique", "Alerte HSE immédiate", "red"
    elif z > 2:
        risk, decision, color = "Anomalie", "Inspection terrain", "orange"
    else:
        risk, decision, color = "Normal", "Surveillance continue", "green"

    st.session_state.analysis_done = True
    st.session_state.results = {
        "site": selected_site,
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date": date_img
    }

# ===================== RESULTS =====================
if st.session_state.analysis_done:
    r = st.session_state.results

    st.metric("CH₄ (ppb)", round(r["ch4"], 1))
    st.metric("Z-score", round(r["z"], 2))
    st.markdown(f"### 🟢 Risque : **{r['risk']}**")
    st.write(r["decision"])

    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)
    folium.Circle(
        [lat_site, lon_site],
        radius=3500,
        color=r["color"],
        fill=True
    ).add_to(m)

    folium.Marker([lat_site, lon_site], tooltip=selected_site).add_to(m)
    st_folium(m, width=700, height=450)

    if st.button("📄 Générer le PDF"):
        pdf = generate_hse_pdf(r)
        with open(pdf, "rb") as f:
            st.download_button("Télécharger PDF", f, file_name=os.path.basename(pdf))

# ===================== HISTORIQUE =====================
st.markdown("## 📈 Historique CH₄")
series = get_ch4_series(df_hist)
df_plot = df_hist.copy()
df_plot["CH4"] = series
df_plot["date"] = pd.to_datetime(df_plot.iloc[:, 0])

fig = px.line(df_plot, x="date", y="CH4", title="Évolution CH₄")
st.plotly_chart(fig, use_container_width=True)
