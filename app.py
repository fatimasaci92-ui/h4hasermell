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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Système intelligent de surveillance du méthane (CH₄) – HSE")
st.info("⚠️ Surveillance régionale basée sur Sentinel-5P. Ce système ne remplace pas les inspections terrain.")

# ===================== INIT GEE =====================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ===================== MULTI-SITES =====================
sites = {
    "Hassi R'mel": {"lat": 32.93, "lon": 3.30, "alt": 750},
    "Hasarmin": {"lat": 32.87, "lon": 3.15, "alt": 520}
}

selected_site = st.sidebar.selectbox("📍 Choisir le site", list(sites.keys()))
lat_site = st.sidebar.number_input("Latitude", value=sites[selected_site]["lat"], format="%.6f")
lon_site = st.sidebar.number_input("Longitude", value=sites[selected_site]["lon"], format="%.6f")
alt_site = st.sidebar.number_input("Altitude (m)", value=sites[selected_site]["alt"])

st.sidebar.markdown(f"**Site :** {selected_site}  \n**Coordonnées :** {lat_site}, {lon_site}  \n**Altitude :** {alt_site} m")

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
    col = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
           .filterBounds(geom)
           .filterDate(start, end)
           .select("CH4_column_volume_mixing_ratio_dry_air")
           .sort("system:time_start", False))
    if col.size().getInfo() == 0:
        return None, None
    img = ee.Image(col.first())
    stats = img.reduceRegion(ee.Reducer.max(), geom, 7000, maxPixels=1e9).getInfo()
    ch4 = stats.get("CH4_column_volume_mixing_ratio_dry_air")
    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    return (ch4 * 1000 if ch4 else None), date_img

def detect_anomaly(value, series):
    return (value - series.mean()) / series.std()

def generate_hse_pdf(results, date_img):
    path = f"/tmp/Rapport_CH4_HSE_{selected_site.replace(' ', '_')}.pdf"
    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("Rapport HSE – Surveillance du Méthane (CH₄)", styles["Title"]))
    elements.append(Spacer(1, 12))
    elements.append(Paragraph(f"<b>Site :</b> {selected_site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Latitude :</b> {lat_site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Longitude :</b> {lon_site}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Altitude :</b> {alt_site} m", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date de rapport :</b> {datetime.utcnow().strftime('%Y-%m-%d')}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date image CH₄ :</b> {date_img}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    table = Table([
        ["Indicateur", "Valeur"],
        ["CH₄ (ppb)", f"{results['ch4']:.1f}"],
        ["Z-score", f"{results['z']:.2f}"],
        ["Niveau de risque", results["risk"]],
        ["Action HSE recommandée", results["decision"]],
    ])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("BACKGROUND", (0,1), (-1,-1), colors.whitesmoke),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("⚠️ Rapport basé sur des données satellitaires (Sentinel-5P). Inspection terrain obligatoire.", styles["Italic"]))
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
        decision = "Inspection terrain requise"
        color = "red"
    else:
        risk = "Normal"
        decision = "Surveillance continue"
        color = "green"

    st.session_state.results = {
        "ch4": ch4,
        "z": z,
        "risk": risk,
        "decision": decision,
        "color": color
    }
    st.session_state.analysis_done = True
    st.session_state.date_img = date_img

# ===================== RÉSULTATS =====================
if st.session_state.analysis_done:
    r = st.session_state.results
    date_img = st.session_state.date_img

    st.subheader(f"📊 Résultats – {selected_site}")
    st.metric("CH₄ (ppb)", round(r["ch4"], 1))
    st.metric("Z-score", round(r["z"], 2))
    st.markdown(f"### 🛑 Risque : **{r['risk']}**")
    st.info(f"Action HSE : {r['decision']}")
    st.info(f"Date dernière image CH₄ : {date_img}")

    # ===================== CARTE =====================
    st.subheader("🗺️ Carte du site avec point critique CH₄")
    m = folium.Map(location=[lat_site, lon_site], zoom_start=12)
    if r["z"] > 2:
        folium.Circle(
            location=[lat_site, lon_site],
            radius=3500,
            color="red",
            fill=True,
            fill_opacity=0.4,
            tooltip=f"Point critique CH₄ : {r['ch4']:.1f} ppb"
        ).add_to(m)
    else:
        folium.Circle(
            location=[lat_site, lon_site],
            radius=3500,
            color="green",
            fill=True,
            fill_opacity=0.2,
            tooltip=f"CH₄ normal : {r['ch4']:.1f} ppb"
        ).add_to(m)
    st_folium(m, width=850, height=500)

    # ===================== PDF =====================
    if st.button("📄 Générer le rapport PDF HSE"):
        pdf_path = generate_hse_pdf(r, date_img)
        with open(pdf_path, "rb") as f:
            st.download_button(
                "⬇️ Télécharger le rapport PDF",
                f,
                file_name=os.path.basename(pdf_path)
            )
