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
st.info("⚠️ Surveillance régionale basée sur Sentinel-5P. Validation terrain obligatoire.")

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
st.sidebar.header("📍 Paramètres")
sites = {
    "Hassi R'mel": (32.93, 3.30),
    "Autre Site": (32.50, 3.20)
}
selected_site = st.sidebar.selectbox("Site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORIQUE =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

def get_ch4_series(df):
    for c in df.columns:
        if "ch4" in c.lower():
            return df[c]
    raise ValueError("Colonne CH4 introuvable")

# ===================== SESSION =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
    st.session_state.results = {}

# ===================== FONCTIONS =====================
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
    val = img.reduceRegion(
        ee.Reducer.mean(), geom, 7000, maxPixels=1e9
    ).getInfo()

    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    ch4 = val.get("CH4_column_volume_mixing_ratio_dry_air")

    return (ch4 * 1000 if ch4 else None), date_img

def detect_anomaly(val, series):
    return (val - series.mean()) / series.std()

def get_active_flares(lat, lon, days_back=7):
    geom = ee.Geometry.Point([lon, lat]).buffer(10000)
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    fires = (
        ee.ImageCollection("NOAA/VIIRS/001/VNP14IMGTDL_NRT")
        .filterBounds(geom)
        .filterDate(start, end)
        .select("Bright_ti4")
    )

    def to_points(img):
        return img.gt(330).selfMask().reduceToVectors(
            geometry=geom,
            scale=375,
            geometryType="centroid",
            maxPixels=1e9
        )

    return fires.map(to_points).flatten()

def generate_hse_pdf(results, site, lat, lon):
    path = f"/tmp/Rapport_CH4_HSE_{site.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    el = []

    el.append(Paragraph("Rapport HSE – Surveillance CH₄", styles["Title"]))
    el.append(Spacer(1, 12))
    el.append(Paragraph(f"<b>Site :</b> {site}", styles["Normal"]))
    el.append(Paragraph(f"<b>Coordonnées :</b> {lat}, {lon}", styles["Normal"]))
    el.append(Paragraph(f"<b>Date :</b> {results['date_img']}", styles["Normal"]))
    el.append(Spacer(1, 12))

    table = Table([
        ["Indicateur", "Valeur"],
        ["CH₄ (ppb)", f"{results['ch4']:.1f}"],
        ["Z-score", f"{results['z']:.2f}"],
        ["Risque", results["risk"]],
        ["Décision", results["decision"]],
    ])

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightblue)
    ]))

    el.append(table)
    doc.build(el)
    return path

# ===================== ANALYSE =====================
if st.button("🚀 Lancer l’analyse"):
    ch4, date_img = get_latest_ch4(lat_site, lon_site)
    series = get_ch4_series(df_hist)

    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "Historique CSV"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk, decision, color = "Critique", "Alerte HSE immédiate", "red"
    elif z > 2:
        risk, decision, color = "Anomalie", "Inspection terrain", "orange"
    else:
        risk, decision, color = "Normal", "Surveillance continue", "green"

    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date_img": date_img
    }
    st.session_state.analysis_done = True

# ===================== RÉSULTATS =====================
if st.session_state.analysis_done:
    r = st.session_state.results

    st.metric("CH₄ (ppb)", round(r["ch4"], 1))
    st.metric("Z-score", round(r["z"], 2))
    st.markdown(f"### 🛑 Risque : **{r['risk']}**")
    st.info(f"Action : {r['decision']}")

    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)
    folium.Circle([lat_site, lon_site], 3500, color=r["color"], fill=True).add_to(m)
    folium.Marker([lat_site, lon_site], tooltip=selected_site).add_to(m)

    flares = get_active_flares(lat_site, lon_site)

    def draw_flares(fc):
        def cb(fc_json):
            for f in fc_json["features"]:
                lon_f, lat_f = f["geometry"]["coordinates"]
                folium.Marker(
                    [lat_f, lon_f],
                    icon=folium.Icon(color="red", icon="fire")
                ).add_to(m)
            st_folium(m, width=750, height=450)
        fc.evaluate(cb)

    draw_flares(flares)

    if st.button("📄 Générer PDF HSE"):
        pdf = generate_hse_pdf(r, selected_site, lat_site, lon_site)
        with open(pdf, "rb") as f:
            st.download_button("⬇️ Télécharger PDF", f, file_name=os.path.basename(pdf))

# ===================== GRAPHIQUE =====================
st.markdown("## 📈 Historique CH₄")
series = get_ch4_series(df_hist)
df_hist["date"] = pd.to_datetime(df_hist.iloc[:, 0])
df_hist["CH4_ppb"] = series

fig = px.line(df_hist, x="date", y="CH4_ppb")
fig.add_hline(y=series.mean(), line_dash="dash")
st.plotly_chart(fig, use_container_width=True)

# ===================== ASSISTANT =====================
st.markdown("## 🤖 Assistant HSE")
q = st.text_input("Votre question")
if st.button("Analyser"):
    st.info("Analyse basée sur Sentinel-5P, historique et règles HSE.")
