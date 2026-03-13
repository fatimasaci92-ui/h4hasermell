# ===================== IMPORTS =====================
import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
import requests
import json
import os
import ee
import tempfile
from datetime import datetime
import matplotlib.pyplot as plt
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet
import io

# ===================== CONFIG =====================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ===================== INIT GEE =====================
ee_available = True
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    ee_available = False
    st.warning(f"Google Earth Engine non initialisé : {e}")

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

# ===================== ZONE =====================
st.sidebar.header("📍 Zone d'analyse")
zone = st.sidebar.selectbox("Choisir la zone", ["Nord", "Centre", "Sud"])
if zone == "Nord":
    lon_min, lon_max = 3.18, 3.81
    lat_min, lat_max = 33.01, 33.28
elif zone == "Centre":
    lon_min, lon_max = 3.14, 3.61
    lat_min, lat_max = 32.75, 33.01
else:  # Sud
    lon_min, lon_max = 2.92, 3.61
    lat_min, lat_max = 32.75, 32.89

# ===================== SESSION STATE =====================
if "ch4_day" not in st.session_state:
    st.session_state.ch4_day = None
    st.session_state.date_img_day = None
    st.session_state.action_day = None
    st.session_state.no_pass_today = False

# ===================== FONCTIONS =====================
def get_latest_ch4_from_gee(latitude, longitude, days_back=60):
    if not ee_available:
        return None, None, True
    try:
        point = ee.Geometry.Point([longitude, latitude])
        end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
        start = end.advance(-days_back, "day")
        collection = (
            ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
            .filterBounds(point)
            .filterDate(start, end)
        )
        image = collection.mean()
        stats = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=point,
            scale=7000,
            maxPixels=1e9
        )
        ch4_ppb = stats.get("CH4_column_volume_mixing_ratio_dry_air").getInfo()
        date_img = collection.first().get("system:time_start").getInfo()
        date_img = datetime.utcfromtimestamp(date_img/1000).strftime("%Y-%m-%d")
        return ch4_ppb, date_img, False
    except:
        return None, None, True

def generate_professional_pdf(site_name, date_img, ch4_value, action, altitude, responsable="HSE Manager"):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    story.append(Paragraph(f"<b>Site :</b> {site_name}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date du rapport :</b> {now}", styles["Normal"]))
    story.append(Paragraph(f"<b>Date image satellite :</b> {date_img}", styles["Normal"]))
    story.append(Paragraph(f"<b>Altitude :</b> {altitude} m", styles["Normal"]))
    story.append(Paragraph(f"<b>Responsable action :</b> {responsable}", styles["Normal"]))
    story.append(Spacer(1,12))
    story.append(Paragraph(
        "Ce rapport présente la surveillance du méthane (CH₄) sur le site, "
        "les valeurs mesurées, et les actions correctives recommandées. "
        "Les seuils HSE sont : Élevé ≥1850 ppb, Critique ≥1900 ppb. "
        "Le suivi quotidien permet de détecter rapidement toute anomalie et de sécuriser le site.",
        styles["Normal"]
    ))
    story.append(Spacer(1,12))
    data_table = [["Paramètre", "Valeur"], ["CH₄ (ppb)", f"{ch4_value:.1f}"], ["Action HSE", action]]
    story.append(Table(data_table))
    story.append(Spacer(1,12))
    doc.build(story)
    buffer.seek(0)
    return buffer

def get_latest_carbon_mapper_plumes(lon_min, lon_max, lat_min, lat_max, date_gee):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200 and response.text.strip() != "":
            data = response.json()
            if "features" in data and isinstance(data["features"], list):
                plumes = pd.json_normalize(data["features"])
                coords = plumes["geometry.coordinates"]
                plumes["lon"] = coords.apply(lambda x: x[0])
                plumes["lat"] = coords.apply(lambda x: x[1])
                
                # convertir la date de plume
                plumes["date"] = pd.to_datetime(plumes["properties.observation_date"])
                date_gee_dt = pd.to_datetime(date_gee)
                
                # garder uniquement les plumes ≤ date GEE
                plumes = plumes[plumes["date"] <= date_gee_dt]
                
                # filtrer par zone
                plumes_zone = plumes[
                    (plumes["lon"] >= lon_min) & (plumes["lon"] <= lon_max) &
                    (plumes["lat"] >= lat_min) & (plumes["lat"] <= lat_max)
                ]
                
                if not plumes_zone.empty:
                    # prendre la plume la plus récente avant la date GEE
                    latest_plume = plumes_zone.loc[plumes_zone["date"].idxmax()]
                    return pd.DataFrame([latest_plume])
                else:
                    return pd.DataFrame()
            else:
                return pd.DataFrame()
        else:
            st.warning(f"Erreur connexion Carbon Mapper : statut {response.status_code}")
            return pd.DataFrame()
    except requests.exceptions.RequestException as e:
        st.warning(f"Erreur connexion Carbon Mapper : {e}")
        return pd.DataFrame()

# ===================== ANALYSE DU JOUR =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser CH₄ du jour"):
    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)
    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible")
    elif no_pass_today:
        st.warning("☁️ Pas de passage satellite valide aujourd’hui")
    else:
        st.success(f"CH₄ : {ch4:.1f} ppb (image du {date_img})")
        if ch4 >= 1900:
            st.error("⚠️ Niveau critique de CH₄ !")
            action = "Alerter et stopper opérations"
        else:
            action = "Surveillance continue"
        st.session_state.ch4_day = ch4
        st.session_state.date_img_day = date_img
        st.session_state.action_day = action

    # ===================== CARBON MAPPER =====================
    st.subheader("Fuites CH₄ détectées (Carbon Mapper)")
    plumes_zone = get_latest_carbon_mapper_plumes(lon_min, lon_max, lat_min, lat_max, date_img)
    if plumes_zone.empty:
        st.info(f"Aucune fuite CH₄ proche de la date GEE dans la zone {zone}.")
    else:
        st.dataframe(plumes_zone[["lat","lon","properties.emission_rate","date"]])
        m = folium.Map(location=[(lat_min+lat_max)/2,(lon_min+lon_max)/2], zoom_start=10)
        for i,row in plumes_zone.iterrows():
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=6,
                color="red",
                fill=True,
                popup=f"Emission: {row['properties.emission_rate']} kg/h\nDate: {row['date'].date()}"
            ).add_to(m)
        st_folium(m, width=700, height=500)

# ===================== PDF =====================
st.markdown("## 📄 Générer PDF Professionnel")
if st.button("Télécharger PDF Professionnel"):
    if st.session_state.ch4_day is None:
        st.warning("Lancez d'abord l'analyse du jour")
    else:
        pdf_buffer = generate_professional_pdf(
            site_name,
            st.session_state.date_img_day,
            st.session_state.ch4_day,
            st.session_state.action_day,
            altitude
        )
        st.download_button(
            "⬇️ Télécharger le PDF Professionnel",
            pdf_buffer,
            f"Rapport_HSE_CH4_{site_name}_{st.session_state.date_img_day}.pdf",
            "application/pdf"
        )
