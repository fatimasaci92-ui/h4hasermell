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
st.info("⚠️ Surveillance régionale Sentinel-5P – validation terrain obligatoire.")

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
    "Autre site": (32.50, 3.20)
}

selected_site = st.sidebar.selectbox("Site", list(sites.keys()))
lat_site, lon_site = sites[selected_site]

# ===================== HISTORICAL DATA =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    raise ValueError("Colonne CH4 non trouvée")

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

    imgs = col.toList(col.size())

    for i in range(col.size().getInfo()):
        img = ee.Image(imgs.get(i))
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

        val = img.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=geom,
            scale=7000,
            maxPixels=1e9
        ).get("CH4_column_volume_mixing_ratio_dry_air")

        val = val.getInfo() if val else None

        if val is not None:
            return val * 1000, date_img

    return None, None

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

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

def log_hse_alert(site, lat, lon, ch4, z, risk, decision):
    path = "alerts_hse.csv"
    row = {
        "datetime": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "site": site,
        "lat": lat,
        "lon": lon,
        "ch4_ppb": round(ch4, 2),
        "z_score": round(z, 2),
        "risk": risk,
        "decision": decision
    }

    if os.path.exists(path):
        df = pd.read_csv(path)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])

    df.to_csv(path, index=False)

def generate_hse_pdf(results, site, lat, lon):
    path = f"/tmp/Rapport_CH4_{site.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Rapport HSE – Surveillance CH₄", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Site :</b> {site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Coordonnées :</b> {lat}, {lon}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date :</b> {results['date_img']}", styles["Normal"]))
    elements.append(Spacer(1, 12))

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

    elements.append(table)
    doc.build(elements)
    return path

# ===================== ANALYSIS =====================
if st.button("🚀 Lancer l’analyse"):
    series = get_ch4_series(df_hist)
    ch4, date_img = get_latest_ch4(lat_site, lon_site)

    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "Historique CSV"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk, decision, color = "Critique", "Alerte HSE immédiate", "red"
        log_hse_alert(selected_site, lat_site, lon_site, ch4, z, risk, decision)
    elif z > 2:
        risk, decision, color = "Anomalie", "Inspection terrain", "orange"
    else:
        risk, decision, color = "Normal", "Surveillance continue", "green"

    st.session_state.analysis_done = True
    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color,
        "date_img": date_img
    }

# ===================== RESULTS =====================
if st.session_state.analysis_done:
    r = st.session_state.results

    st.metric("CH₄ (ppb)", round(r["ch4"], 1))
    st.metric("Z-score", round(r["z"], 2))
    st.markdown(f"### Risque : <span style='color:{r['color']}'>{r['risk']}</span>", unsafe_allow_html=True)
    st.info(f"Action : {r['decision']}")

    m = folium.Map(location=[lat_site, lon_site], zoom_start=6)
    folium.Circle([lat_site, lon_site], 3500, color=r["color"], fill=True).add_to(m)
    folium.Marker([lat_site, lon_site], tooltip=selected_site).add_to(m)

    flares = get_active_flares(lat_site, lon_site)

    def show_flares(fc):
        def cb(fc_json):
            for f in fc_json["features"]:
                lon_f, lat_f = f["geometry"]["coordinates"]
                folium.Marker(
                    [lat_f, lon_f],
                    icon=folium.Icon(color="red", icon="fire"),
                    tooltip="Torche VIIRS"
                ).add_to(m)
            st_folium(m, width=750, height=450)
        fc.evaluate(cb)

    show_flares(flares)

    if st.button("📄 Générer PDF HSE"):
        pdf = generate_hse_pdf(r, selected_site, lat_site, lon_site)
        with open(pdf, "rb") as f:
            st.download_button("⬇️ Télécharger PDF", f, file_name=os.path.basename(pdf))

# ===================== HISTORIQUE =====================
st.markdown("## 📋 Historique des alertes")
if os.path.exists("alerts_hse.csv"):
    df_alerts = pd.read_csv("alerts_hse.csv")
    st.dataframe(df_alerts, use_container_width=True)

# ===================== GRAPHIQUE =====================
st.markdown("## 📈 Évolution CH₄")
series = get_ch4_series(df_hist)
df_hist["CH4_ppb"] = series
df_hist["date"] = pd.to_datetime(df_hist.iloc[:, 0])

fig = px.line(df_hist, x="date", y="CH4_ppb")
fig.add_hline(y=series.mean(), line_dash="dash")
st.plotly_chart(fig, use_container_width=True)

