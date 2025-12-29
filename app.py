# ===================== IMPORTS =====================
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
import folium
from streamlit_folium import st_folium

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ===================== INIT GEE =====================
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

# ===================== INFOS SITE =====================
st.sidebar.header("📍 Paramètres du site")
sites = {
    "Hassi R'mel": {"lat": 32.93, "lon": 3.30, "alt": 750},
    "Hasarmin": {"lat": 32.87, "lon": 3.15, "alt": 520}
}
selected_site = st.sidebar.selectbox("Choisir le site", list(sites.keys()))
latitude = st.sidebar.number_input("Latitude", value=sites[selected_site]["lat"], format="%.6f")
longitude = st.sidebar.number_input("Longitude", value=sites[selected_site]["lon"], format="%.6f")
altitude = st.sidebar.number_input("Altitude (m)", value=sites[selected_site]["alt"])
site_name = st.sidebar.text_input("Nom du site", value=selected_site)

# ===================== CHEMINS =====================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"
csv_monthly = "data/2020 2024/CH4_HassiRmel_monthly_2020_2024.csv"

# ===================== SESSION STATE =====================
if "ch4_day" not in st.session_state:
    st.session_state.ch4_day = None
    st.session_state.date_img_day = None
    st.session_state.action_day = None
    st.session_state.no_pass_today = False

# ===================== FONCTIONS =====================
def get_latest_ch4_from_gee(lat, lon, days_back=60):
    point = ee.Geometry.Point([lon, lat])
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
        ch4_ppb = float(v) * 1000
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today
        return ch4_ppb, date_img, no_pass_today
    return None, None, True

def generate_professional_pdf(site_name, date_img, ch4_value, action, altitude, responsable="HSE Manager"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<b>Rapport Professionnel HSE – Surveillance CH₄</b>", styles["Title"]))
    story.append(Spacer(1,12))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(f"<b>Site :</b> {site_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date du rapport :</b> {now}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date image satellite :</b> {date_img}", styles["Normal"]))
    story.append(Paragraph(f"<b>Altitude :</b> {altitude} m", styles["Normal"]))
    story.append(Paragraph(f"<b>Responsable action :</b> {responsable}", styles["Normal"]))
    story.append(Spacer(1,12))

    data_table = [
        ["Paramètre", "Valeur"],
        ["CH₄ mesuré (ppb)", f"{ch4_value:.1f}"],
        ["Anomalie détectée", "Oui" if ch4_value >= 1900 else "Non"],
        ["Action corrective", action]
    ]
    t = Table(data_table, hAlign="LEFT", colWidths=[200,250])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONTSIZE',(0,0),(-1,0),12),
        ('BOTTOMPADDING',(0,0),(-1,0),6),
        ('BACKGROUND',(0,1),(-1,-1),colors.lightblue),
        ('GRID',(0,0),(-1,-1),1,colors.black),
    ]))
    story.append(t)
    story.append(Spacer(1,12))
    doc.build(story)
    buffer.seek(0)
    return buffer

# ===================== SECTION A : Données historiques =====================
st.markdown("## 📑 Données historiques")
if os.path.exists(csv_hist):
    df_hist = pd.read_csv(csv_hist)
    st.dataframe(df_hist.head(20))
else:
    st.warning("CSV historique introuvable")

# ===================== SECTION B : Analyse CH₄ du jour =====================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE)")
if st.button("Analyser CH₄ du jour"):
    st.session_state.ch4_day, st.session_state.date_img_day, st.session_state.no_pass_today = get_latest_ch4_from_gee(latitude, longitude)
    if st.session_state.ch4_day is None:
        st.error("⚠️ Aucune image satellite disponible")
    else:
        if st.session_state.no_pass_today:
            st.warning(f"☁️ Pas de passage satellite aujourd’hui. Dernière image : {st.session_state.date_img_day}")
        st.success(f"CH₄ : **{st.session_state.ch4_day:.1f} ppb** (image du {st.session_state.date_img_day})")
        if st.session_state.ch4_day >= 1900:
            st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
            st.session_state.action_day = "Alerter, sécuriser la zone et stopper opérations"
        else:
            st.session_state.action_day = "Surveillance continue"

# Affichage permanent si analyse déjà faite
if st.session_state.ch4_day is not None:
    df_day = pd.DataFrame([{
        "Date image": st.session_state.date_img_day,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "Altitude (m)": altitude,
        "CH₄ (ppb)": round(st.session_state.ch4_day, 2),
        "Anomalie": "Oui" if st.session_state.ch4_day >= 1900 else "Non",
        "Action HSE": st.session_state.action_day
    }])
    st.table(df_day)

    # Carte avec cercle critique
    st.subheader("🗺️ Carte du site avec zone critique CH₄")
    m = folium.Map(location=[latitude, longitude], zoom_start=12)
    color_circle = "red" if st.session_state.ch4_day >= 1900 else "green"
    folium.Circle(
        location=[latitude, longitude],
        radius=3500,
        color=color_circle,
        fill=True,
        fill_opacity=0.4,
        tooltip=f"CH₄ : {st.session_state.ch4_day:.1f} ppb"
    ).add_to(m)
    folium.Marker([latitude, longitude], tooltip=site_name).add_to(m)
    st_folium(m, width=800, height=500)

    # PDF
    st.subheader("📄 Générer PDF Professionnel")
    pdf_buffer = generate_professional_pdf(site_name, st.session_state.date_img_day, st.session_state.ch4_day, st.session_state.action_day, altitude)
    st.download_button(
        "⬇️ Télécharger le PDF Professionnel",
        pdf_buffer,
        f"Rapport_HSE_CH4_{site_name}_{st.session_state.date_img_day}.pdf",
        "application/pdf"
    )

# ===================== SECTION C : Graphiques temporels =====================
st.markdown("## 📊 Graphiques temporels 2020–2025")
if os.path.exists(csv_annual):
    df_a = pd.read_csv(csv_annual)
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(df_a["year"], df_a["CH4_mean"], marker="o")
    ax.axhline(1850, linestyle="--", color="orange", label="Seuil HSE élevé")
    ax.axhline(1900, linestyle="--", color="red", label="Seuil HSE critique")
    ax.set_title("CH₄ annuel moyen")
    ax.set_xlabel("Année")
    ax.set_ylabel("CH₄ (ppb)")
    ax.legend()
    st.pyplot(fig)
else:
    st.warning("CSV annuel introuvable")

if os.path.exists(csv_monthly):
    df_m = pd.read_csv(csv_monthly)
    df_m[df_m.columns[0]] = pd.to_datetime(df_m[df_m.columns[0]])
    fig, ax = plt.subplots(figsize=(10,4))
    ax.plot(df_m[df_m.columns[0]], df_m[df_m.columns[1]], marker="o")
    ax.axhline(1850, linestyle="--", color="orange", label="Seuil HSE élevé")
    ax.axhline(1900, linestyle="--", color="red", label="Seuil HSE critique")
    ax.set_title("CH₄ mensuel moyen")
    ax.set_xlabel("Date")
    ax.set_ylabel("CH₄ (ppb)")
    ax.legend()
    plt.xticks(rotation=45)
    st.pyplot(fig)
else:
    st.warning("CSV mensuel introuvable")
