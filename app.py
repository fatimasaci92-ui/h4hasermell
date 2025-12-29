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
import matplotlib.pyplot as plt

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")

st.info(
    "⚠️ Surveillance régionale basée sur Sentinel-5P. "
    "Ce système ne remplace pas les inspections terrain."
)

# ===================== INIT GEE =====================
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

# ===================== SITE : HASSI R'MEL =====================
site_name = "Hassi R'mel"
lat_site = 32.93
lon_site = 3.30
alt_site = 750  # mètres

st.sidebar.header("📍 Site surveillé")
st.sidebar.markdown(
    f"""
    **Site :** {site_name}  
    **Latitude :** {lat_site}  
    **Longitude :** {lon_site}  
    **Altitude :** {alt_site} m
    """
)

# ===================== DONNÉES HISTORIQUES =====================
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
df_hist = pd.read_csv(csv_hist)

def get_ch4_series(df):
    for col in df.columns:
        if "ch4" in col.lower():
            return df[col]
    raise ValueError("Colonne CH₄ introuvable dans le CSV")

# ===================== SESSION =====================
if "analysis_done" not in st.session_state:
    st.session_state.analysis_done = False
    st.session_state.results = {}

# ===================== FONCTIONS =====================
def get_latest_ch4(lat, lon, days_back=60):
    geom = ee.Geometry.Point([lon, lat]).buffer(4000)
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
    stats = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=geom,
        scale=7000,
        maxPixels=1e9
    ).getInfo()

    ch4 = stats.get("CH4_column_volume_mixing_ratio_dry_air")
    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    if ch4 is None:
        return None, date_img

    return ch4 * 1000, date_img  # ppb

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

def generate_hse_pdf(results):
    path = f"/tmp/Rapport_CH4_HSE_Hassi_Rmel.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(
        "Rapport HSE – Surveillance du Méthane (CH₄)",
        styles["Title"]
    ))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"<b>Site :</b> {site_name}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Latitude :</b> {lat_site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Longitude :</b> {lon_site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Altitude :</b> {alt_site} m", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Date d’analyse :</b> {results['date_img']}",
        styles["Normal"]
    ))

    elements.append(Spacer(1, 12))

    table = Table(
        [
            ["Indicateur", "Valeur"],
            ["CH₄ (ppb)", f"{results['ch4']:.1f}"],
            ["Z-score", f"{results['z']:.2f}"],
            ["Niveau de risque", results["risk"]],
            ["Action HSE recommandée", results["decision"]],
        ],
        colWidths=[220, 260]
    )

    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(
        "⚠️ Rapport basé sur des données satellitaires (Sentinel-5P). "
        "Une inspection terrain est obligatoire pour confirmation.",
        styles["Italic"]
    ))

    doc.build(elements)
    return path

# ===================== ANALYSE =====================
if st.button("🚀 Lancer l’analyse"):
    series = get_ch4_series(df_hist)
    ch4, date_img = get_latest_ch4(lat_site, lon_site)

    if ch4 is None:
        ch4 = series.iloc[-1]
        date_img = "Historique CSV"

    z = detect_anomaly(ch4, series)

    if z > 3:
        risk = "Critique"
        decision = "Alerte HSE immédiate – intervention urgente"
        color = "red"
    elif z > 2:
        risk = "Anomalie"
        decision = "Inspection terrain ciblée requise"
        color = "orange"
    else:
        risk = "Normal"
        decision = "Surveillance continue"
        color = "green"

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

    st.subheader("📊 Résultats – Hassi R'mel")

    c1, c2 = st.columns(2)
    c1.metric("CH₄ (ppb)", round(r["ch4"], 1))
    c2.metric("Z-score", round(r["z"], 2))

    st.markdown(f"### 🛑 Risque : **{r['risk']}**")
    st.info(f"Action HSE : {r['decision']}")

    # ===================== CARTE – PLAN HASSI R'MEL =====================
    st.subheader("🗺️ Plan du complexe gazier de Hassi R'mel")

    m = folium.Map(location=[lat_site, lon_site], zoom_start=12)

    hassi_rmel_polygon = [
        [32.98, 3.20],
        [32.98, 3.40],
        [32.88, 3.40],
        [32.88, 3.20],
        [32.98, 3.20]
    ]

    folium.Polygon(
        locations=hassi_rmel_polygon,
        color="blue",
        fill=True,
        fill_opacity=0.25,
        tooltip="Périmètre du complexe gazier de Hassi R'mel"
    ).add_to(m)

    folium.Marker(
        [lat_site, lon_site],
        tooltip="Centre du complexe Hassi R'mel",
        icon=folium.Icon(color="red", icon="industry")
    ).add_to(m)

    st_folium(m, width=850, height=500)

    # ===================== PDF =====================
    if st.button("📄 Générer le rapport PDF HSE"):
        pdf_path = generate_hse_pdf(r)
        with open(pdf_path, "rb") as f:
            st.download_button(
                "⬇️ Télécharger le rapport PDF",
                f,
                file_name=os.path.basename(pdf_path)
            )

# ===================== GRAPHIQUE HISTORIQUE =====================
st.markdown("## 📈 Évolution historique du CH₄")

series = get_ch4_series(df_hist)
df_hist["date"] = pd.to_datetime(df_hist.iloc[:, 0])
df_hist["CH4_ppb"] = series

fig, ax = plt.subplots()
ax.plot(df_hist["date"], df_hist["CH4_ppb"])
ax.axhline(series.mean(), linestyle="--")
ax.set_xlabel("Date")
ax.set_ylabel("CH₄ (ppb)")
ax.set_title("Évolution historique du CH₄ – Hassi R'mel")

st.pyplot(fig)
