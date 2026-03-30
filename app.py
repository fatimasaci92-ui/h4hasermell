# ================= app.py — VERSION FINALE CLEAN =================

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.pagesizes import A4
import json
import tempfile
import requests
import folium
from streamlit_folium import st_folium
from tensorflow.keras.models import load_model
import ee

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= LOAD MODEL =================
MODEL_PATH = "AI_model/cnn_model.h5"
try:
    cnn_model = load_model(MODEL_PATH)
except:
    cnn_model = None
st.write("Modèle chargé :", cnn_model is not None)

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

# ================= CARBON MAPPER TOKEN =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")
if not CARBON_API_TOKEN:
    st.error("❌ Token Carbon Mapper manquant")

# ================= INPUT =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")
zone_choice = st.selectbox("Choisir la zone", ["Centre", "Sud", "Nord"])

# ================= ZONES (LISTES SIMPLES) =================
zone_centre = [[32.7566,3.3769],[32.7566,3.6115],[33.0134,3.6063],[33.0240,2.9338],[32.8939,2.9275],[32.8895,3.3769]]
zone_sud = [[32.4509,2.8856],[32.4509,3.3796],[32.8837,3.3796],[32.8837,2.8856]]
zone_nord = [[33.0135,3.1851],[33.2829,3.1848],[33.2785,3.8109],[33.0135,3.8107]]

zone_map = {"Centre": zone_centre, "Sud": zone_sud, "Nord": zone_nord}
selected_zone = zone_map[zone_choice]

# ================= FONCTIONS =================
def point_in_zone(lat, lon, zone_coords):
    """Détection simple si un point est dans un rectangle approximatif"""
    lats = [pt[0] for pt in zone_coords]
    lons = [pt[1] for pt in zone_coords]
    return min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons)

def get_latest_ch4_from_gee(lat, lon, days_back=60):
    point = ee.Geometry.Point([lon, lat])
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")
    collection = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                  .filterBounds(point)
                  .filterDate(start,end)
                  .select("CH4_column_volume_mixing_ratio_dry_air")
                  .sort("system:time_start", False))
    size = collection.size().getInfo()
    if size==0: return None, None
    img = ee.Image(collection.toList(size).get(0))
    date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    value = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=7000).get("CH4_column_volume_mixing_ratio_dry_air")
    try:
        ch4 = float(value.getInfo())
    except:
        ch4 = None
    return ch4, date_img

def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"
    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {"gas":"CH4","limit":20,"bbox":f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code!=200: return []
        plumes=[]
        for f in r.json().get("features",[]):
            coords = f["geometry"]["coordinates"]
            props = f["properties"]
            plumes.append({"lat":coords[1],"lon":coords[0],"emission":props.get("emission_rate",0)})
        return plumes
    except:
        return []

# ================= SECTION E — CH₄ DU JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour")

if st.button("Analyser CH₄"):

    st.info("Analyse en cours...")
    ch4, date_img = get_latest_ch4_from_gee(latitude, longitude)
    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible")
        st.stop()

    # IA simple
    prediction = None
    if cnn_model:
        image = np.full((64,64), ch4)/3000.0
        image = image.reshape(1,64,64,1)
        prediction = cnn_model.predict(image)[0][0]

    # Historique CSV
    ch4_mean = None
    csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)
        for col in ["CH4","ch4","mean"]:
            if col in df_hist.columns:
                ch4_mean = df_hist[col].mean()
                break

    # Détection fuite zone
    fuite_zone = False
    if prediction and prediction>0.5:
        fuite_zone = point_in_zone(latitude, longitude, selected_zone)

    # Affichage résultats
    st.success(f"📅 Date : {date_img}")
    st.success(f"🛰️ CH₄ : {ch4:.1f} ppb")
    if ch4_mean: st.info(f"📊 Moyenne historique : {ch4_mean:.1f} ppb")
    if prediction: st.write(f"🧠 Score IA : {prediction:.2f}")
    if fuite_zone: st.error(f"🚨 Fuite DANS zone {zone_choice}")
    elif prediction and prediction>0.5: st.warning(f"⚠️ Fuite HORS zone {zone_choice}")

    # Plumes Carbon Mapper
    plumes=[]
    if prediction and prediction>0.5:
        plumes=get_ch4_plumes_carbonmapper(latitude, longitude)
        if plumes: st.error(f"🔥 {len(plumes)} plume(s) détectée(s)")
        else: st.warning("Aucune plume détectée")

    # Tableau final
    df_day=pd.DataFrame([{
        "Date": date_img,
        "CH4": ch4,
        "Moyenne": ch4_mean,
        "Zone": zone_choice,
        "Risque": "Critique" if prediction and prediction>0.7 else ("Élevé" if prediction and prediction>0.5 else "Normal")
    }])
    st.table(df_day)

    # Stockage session
    st.session_state["ch4"]=ch4
    st.session_state["plumes"]=plumes
    st.session_state["action"]=df_day["Risque"].values[0]

# ================= SECTION G — CARTE =================
st.markdown("## 🌍 Carte interactive CH₄")

if st.button("Afficher carte"):

    m = folium.Map(location=[latitude, longitude], zoom_start=6)
    folium.TileLayer(tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri").add_to(m)

    # Zones
    folium.Polygon(zone_centre, color="red", fill=True, fill_opacity=0.1, popup="Centre").add_to(m)
    folium.Polygon(zone_sud, color="green", fill=True, fill_opacity=0.1, popup="Sud").add_to(m)
    folium.Polygon(zone_nord, color="blue", fill=True, fill_opacity=0.1, popup="Nord").add_to(m)

    # Site
    folium.Marker([latitude, longitude], popup=site_name, icon=folium.Icon(color="blue")).add_to(m)

    # Heatmap CH₄
    heat=[]
    if "ch4" in st.session_state: heat.append([latitude, longitude, st.session_state["ch4"]])

    # Plumes
    coords=[]
    if "plumes" in st.session_state:
        for p in st.session_state["plumes"]:
            coords.append([p["lat"],p["lon"]])
            heat.append([p["lat"],p["lon"],p["emission"]])
            folium.Marker([p["lat"],p["lon"]], popup=f"Plume: {p['emission']} kg/h", icon=folium.Icon(color="red")).add_to(m)

    # HeatMap
    if heat:
        from folium.plugins import HeatMap
        HeatMap(heat,radius=25).add_to(m)

    # Zoom auto
    if coords: m.fit_bounds(coords)
    else: m.location=[latitude,longitude]; m.zoom_start=8

    st_folium(m, width=750, height=500)
