# ================= app.py — VERSION FINALE PROPRE =================

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
import requests
from tensorflow.keras.models import load_model
import folium
from streamlit_folium import st_folium
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

# ================= CARBON MAPPER =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")
if not CARBON_API_TOKEN:
    st.error("❌ Token Carbon Mapper manquant")

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INPUT =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= PATHS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"

# ================= GEE FUNCTION =================
def get_latest_ch4_from_gee(latitude, longitude, days_back=60):
    point = ee.Geometry.Point([longitude, latitude])
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

        ch4_ppb = float(v)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today

        return ch4_ppb, date_img, no_pass_today

    return None, None, True

# ================= CARBON FUNCTION =================
def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"
    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {"gas": "CH4", "limit": 20,
              "bbox": f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code != 200:
            return []

        data = response.json()
        plumes = []

        for item in data.get("features", []):
            coords = item["geometry"]["coordinates"]
            props = item["properties"]
            plumes.append({
                "lat": coords[1],
                "lon": coords[0],
                "emission": props.get("emission_rate", 0)
            })

        return plumes
    except:
        return []

# ================= SECTION A =================
st.markdown("## 📁 Section A — Données")
if st.button("Afficher dossiers"):
    for root, dirs, files in os.walk(DATA_DIR):
        st.write(root)
        for f in files:
            st.write(" └─", f)

# ================= SECTION B =================
st.markdown("## 📑 Section B — CSV")
if st.button("Afficher CSV"):
    if os.path.exists(csv_hist):
        df = pd.read_csv(csv_hist)
        st.dataframe(df.head())
    else:
        st.warning("CSV introuvable")

# ================= SECTION C : Carte CH₄ moyenne =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")

year_mean = st.selectbox(
    "Choisir l'année pour la carte",
    [2020, 2021, 2022, 2023, 2024, 2025]
)

if st.button("Afficher carte CH₄ moyenne"):

    mean_path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"

    if os.path.exists(mean_path):

        with rasterio.open(mean_path) as src:
            img = src.read(1)

        # Nettoyage des valeurs
        img[img <= 0] = np.nan

        # ================= AFFICHAGE PRO =================
        fig, ax = plt.subplots(figsize=(6,5))

        im = ax.imshow(img, cmap="viridis")

        # Barre de couleur (IMPORTANT pour PFE)
        plt.colorbar(im, ax=ax, label="CH₄ (ppb)")

        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")

        st.pyplot(fig)

    else:
        st.warning("Carte CH₄ introuvable")
# ================= SECTION D =================
st.markdown("## 🔎 Analyse annuelle")
if st.button("Analyser année"):
    if os.path.exists(csv_annual):
        df = pd.read_csv(csv_annual)
        st.dataframe(df)

# ================= SECTION E : Analyse CH₄ du jour =================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE + IA + Historique)")

if st.button("Analyser CH₄ du jour"):

    st.info("Analyse en cours...")

    # ================= GEE =================
    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible")
        st.stop()

    # ================= HISTORIQUE =================
    ch4_mean = None

    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)

        # 🔍 Trouver automatiquement la colonne CH4
        possible_cols = ["CH4", "ch4", "CH4_mean", "mean", "value"]

        col_found = None
        for col in possible_cols:
            if col in df_hist.columns:
                col_found = col
                break

        if col_found is not None:
            ch4_mean = df_hist[col_found].mean()
        else:
            st.warning("⚠️ Colonne CH4 introuvable dans le CSV")

    else:
        st.warning("⚠️ Fichier historique introuvable")

    # ================= IA =================
    if cnn_model is not None:
        image = np.full((64, 64), ch4)
        image = image / 3000.0
        image = image.reshape(1, 64, 64, 1)

        prediction = cnn_model.predict(image)[0][0]
    else:
        prediction = None

    # ================= AFFICHAGE =================
    st.success(f"📅 Date satellite : {date_img}")
    st.success(f"🛰️ CH₄ (GEE) : {ch4:.1f} ppb")

    if ch4_mean is not None:
        st.info(f"📊 Moyenne historique : {ch4_mean:.1f} ppb")

    if prediction is not None:
        st.write(f"🧠 Score IA : {prediction:.2f}")

    # ================= DÉCISION =================
    if prediction is not None:
        if prediction > 0.7:
            risk = "Critique (IA)"
            action = "Fuite détectée – intervention urgente"
            st.error("⚠️ IA : fuite détectée !")

        elif prediction > 0.5:
            risk = "Élevé (IA)"
            action = "Inspection recommandée"
            st.warning("⚠️ IA : suspicion de fuite")

        else:
            risk = "Normal (IA)"
            action = "Pas de fuite"
            st.success("✅ IA : pas de fuite")

        # 🔥 Carbon Mapper
        if prediction > 0.5:
            plumes = get_ch4_plumes_carbonmapper(latitude, longitude)

            if len(plumes) > 0:
                st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) !")
                for plume in plumes:
                    st.write(f"- {plume['emission']} kg/h à ({plume['lat']:.4f}, {plume['lon']:.4f})")
            else:
                st.warning("⚠️ Aucune plume détectée par Carbon Mapper")

    else:
        # fallback sans IA
        if ch4 >= 1900:
            risk = "Critique"
            action = "Arrêt + alerte HSE"
        elif ch4 >= 1850:
            risk = "Élevé"
            action = "Inspection urgente"
        else:
            risk = "Normal"
            action = "Surveillance continue"

    # ================= TABLEAU FINAL =================
    df_day = pd.DataFrame([{
        "Date satellite": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ (GEE)": round(ch4, 2),
        "Moyenne historique": round(ch4_mean, 2) if ch4_mean else "N/A",
        "Risque": risk,
        "Action HSE": action
    }])

    st.table(df_day)

    # ================= SAUVEGARDE =================
    st.session_state["ch4"] = ch4
    st.session_state["date_img"] = date_img
    st.session_state["action"] = action
    st.session_state["site_name"] = site_name
    # Calcul concentration moyenne historique (exemple)
    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)
        ch4_mean = df_hist["CH4"].mean()
    else:
        ch4_mean = None

    # ================= IA =================
    prediction = None
    if cnn_model is not None:
        image = np.full((64,64), ch4)
        image = image / 3000.0
        image = image.reshape(1,64,64,1)
        prediction = cnn_model.predict(image)[0][0]

    # ================= Affichage des résultats =================
    st.success(f"CH₄ du jour (GEE) : **{ch4:.1f} ppb** (image du {date_img})")
    if ch4_mean is not None:
        st.info(f"Concentration moyenne historique : {ch4_mean:.1f} ppb")

    if prediction is not None:
        st.write(f"🧠 Score IA : {prediction:.2f}")

    # ================= Décision HSE =================
    if prediction is not None:
        # IA active
        if prediction > 0.7:
            risk = "Critique (IA)"
            action = "Fuite détectée par IA – intervention urgente"
            st.error("⚠️ IA : fuite détectée !")
        elif prediction > 0.5:
            risk = "Élevé (IA)"
            action = "Inspection recommandée (IA)"
            st.warning("⚠️ IA : suspicion de fuite")
        else:
            risk = "Normal (IA)"
            action = "Pas de fuite détectée"
            st.success("✅ IA : pas de fuite")

        # Vérification Carbon Mapper si IA ≥ Élevé
        if prediction > 0.5:
            plumes = get_ch4_plumes_carbonmapper(latitude, longitude)
            st.session_state["plumes"] = plumes
            if len(plumes) > 0:
                st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
                for plume in plumes:
                    st.write(f"- Emission {plume['emission']} kg/h à ({plume['lat']:.4f},{plume['lon']:.4f})")
            else:
                st.warning("⚠️ IA détecte une fuite, mais aucune plume confirmée")
    else:
        # Fallback sans IA
        if ch4 >= 1900:
            risk = "Critique"
            action = "Arrêt + alerte HSE"
        elif ch4 >= 1850:
            risk = "Élevé"
            action = "Inspection urgente"
        else:
            risk = "Normal"
            action = "Surveillance continue"

    # ================= Tableau résumé =================
    df_day = pd.DataFrame([{
        "Date image": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ du jour (ppb)": round(ch4, 2),
        "Concentration moyenne (ppb)": round(ch4_mean,2) if ch4_mean is not None else "N/A",
        "Risque": risk,
        "Action HSE": action
    }])
    st.table(df_day)

    # ================= Stockage session pour PDF =================
    st.session_state["ch4"] = ch4
    st.session_state["date_img"] = date_img
    st.session_state["action"] = action
    st.session_state["site_name"] = site_name
# ================= PDF =================
def generate_pdf(site, date, ch4, action):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph("Rapport CH4", styles["Title"]))
    story.append(Paragraph(f"Site: {site}", styles["Normal"]))
    story.append(Paragraph(f"Date: {date}", styles["Normal"]))
    story.append(Paragraph(f"CH4: {ch4}", styles["Normal"]))
    story.append(Paragraph(f"Action: {action}", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer
# ================= SECTION G : Carte interactive CH₄ =================
st.markdown("## 🌍 Carte interactive – Détection CH₄ & IA")

if st.button("Afficher carte interactive"):

    # Centre carte
    m = folium.Map(location=[latitude, longitude], zoom_start=8)

    # 📍 Marqueur site
    folium.Marker(
        [latitude, longitude],
        popup=f"📍 Site : {site_name}",
        icon=folium.Icon(color="blue")
    ).add_to(m)

    # 🔥 Couleur selon CH4
    if "ch4" in st.session_state:
        ch4_val = st.session_state["ch4"]

        if ch4_val >= 1900:
            color = "red"
        elif ch4_val >= 1850:
            color = "orange"
        else:
            color = "green"

        folium.Circle(
            location=[latitude, longitude],
            radius=5000,
            color=color,
            fill=True,
            fill_opacity=0.4,
            popup=f"CH₄: {ch4_val:.1f} ppb"
        ).add_to(m)

    # ⚠️ Plumes Carbon Mapper
    if "plumes" in st.session_state:
        for plume in st.session_state["plumes"]:
            folium.Marker(
                [plume["lat"], plume["lon"]],
                popup=f"🔥 Plume: {plume['emission']} kg/h",
                icon=folium.Icon(color="red", icon="cloud")
            ).add_to(m)

    # 🧠 IA affichage
    if "action" in st.session_state:
        folium.Marker(
            [latitude, longitude],
            popup=f"🧠 IA: {st.session_state['action']}",
            icon=folium.Icon(color="purple")
        ).add_to(m)

    # Affichage Streamlit
    st_folium(m, width=700, height=500)
