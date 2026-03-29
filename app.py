# ================= app.py — VERSION COMPLÈTE CORRIGÉE =================
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
import requests
from tensorflow.keras.models import load_model
from tensorflow.keras.models import load_model

MODEL_PATH = "AI_model/cnn_model.h5"

try:
    cnn_model = load_model(MODEL_PATH)
except:
    cnn_model = None

st.write("Modèle chargé :", cnn_model is not None)
MODEL_PATH = "AI_model/cnn_model.h5"

st.write("Modèle chargé :", cnn_model is not None)
# ================= INITIALISATION GOOGLE EARTH ENGINE =================
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

# ================= CARBON MAPPER API =================
CARBON_API_TOKEN = st.secrets.get("CARBON_API_TOKEN", "")
if not CARBON_API_TOKEN:
    st.error("❌ Token Carbon Mapper manquant dans secrets.toml")

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= CHEMINS DES FICHIERS =================
DATA_DIR = "data"
csv_hist = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"
csv_annual = "data/2020 2024/CH4_HassiRmel_annual_2020_2024.csv"
csv_monthly = "data/2020 2024/CH4_HassiRmel_monthly_2020_2024.csv"

# ================= FONCTION GEE =================
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

        # ✅ CORRECTION ICI
        ch4_ppb = float(v)

        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today

        return ch4_ppb, date_img, no_pass_today

    return None, None, True

# ================= FONCTION CARBON MAPPER =================
def get_ch4_plumes_carbonmapper(lat, lon):
    url = "https://api.carbonmapper.org/api/v1/catalog/plumes"
    headers = {"Authorization": f"Bearer {CARBON_API_TOKEN}"}
    params = {
        "gas": "CH4",
        "limit": 20,
        "bbox": f"{lon-0.5},{lat-0.5},{lon+0.5},{lat+0.5}"
    }
    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
        if response.status_code == 401:
            st.error("❌ Token Carbon Mapper invalide")
            return []
        if response.status_code != 200:
            st.warning(f"⚠️ API erreur: {response.status_code}")
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
    except Exception as e:
        st.error(f"Erreur Carbon Mapper : {e}")
        return []

# ================= SECTION A : Contenu des dossiers =================
st.markdown("## 📁 Section A — Contenu des données")
if st.button("Afficher les dossiers de données"):
    if os.path.exists(DATA_DIR):
        for root, dirs, files in os.walk(DATA_DIR):
            st.write("📂", root)
            for f in files:
                st.write(" └─", f)
    else:
        st.warning("Dossier data introuvable")

# ================= SECTION B : Aperçu CSV =================
st.markdown("## 📑 Section B — Aperçu des données historiques")
if st.button("Afficher CSV historique"):
    if os.path.exists(csv_hist):
        df_hist = pd.read_csv(csv_hist)
        st.dataframe(df_hist.head(20))
    else:
        st.warning("CSV historique introuvable")

# ================= SECTION C : Carte CH₄ moyenne =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")
year_mean = st.selectbox("Choisir l'année pour la carte", [2020,2021,2022,2023,2024,2025])
if st.button("Afficher carte CH₄ moyenne"):
    mean_path = f"data/Moyenne CH4/CH4_mean_{year_mean}.tif"
    if os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(img, cmap="viridis")
        ax.set_title(f"CH₄ moyen {year_mean}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.warning("Carte CH₄ introuvable")

# ================= SECTION D : Analyse HSE annuelle =================
st.markdown("## 🔎 Section D — Analyse HSE annuelle")
year = st.selectbox("Choisir l'année pour analyse HSE", [2020,2021,2022,2023,2024,2025])
if st.button("Analyser année sélectionnée"):
    if os.path.exists(csv_annual):
        df_year = pd.read_csv(csv_annual)
        if year in df_year["year"].values:
            val = df_year[df_year["year"]==year]["CH4_mean"].values[0]
            if val >= 1900:
                risk = "Critique"
                action = "Arrêt + alerte HSE"
            elif val >= 1850:
                risk = "Élevé"
                action = "Inspection urgente"
            else:
                risk = "Normal"
                action = "Surveillance continue"
            st.success(f"CH₄ moyen {year} : {val:.1f} ppb")
            st.write("Risque :", risk)
            st.write("Action :", action)
        else:
            st.warning("Année non trouvée")
    else:
        st.warning("CSV annuel introuvable")

# ================= SECTION E : Analyse CH₄ du jour =================
st.markdown("## 🔍 Analyse CH₄ du jour (GEE)")

if st.button("Analyser CH₄ du jour"):
    st.info("Analyse en cours...")

    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible")
        st.stop()

    # ================= IA =================
    if cnn_model is not None:
        image = np.full((64,64), ch4)
        image = image / 3000.0
        image = image.reshape(1,64,64,1)

        prediction = cnn_model.predict(image)[0][0]
    else:
        prediction = None

    # ================= Affichage =================
    st.success(f"CH₄ : **{ch4:.1f} ppb** (image du {date_img})")

    if prediction is not None:
        st.write(f"🧠 Score IA : {prediction:.2f}")

    # ================= Décision =================
     if prediction is not None:
    if prediction > 0.7:
    risk = "Critique (IA)"
    action = "Fuite détectée par IA – intervention urgente"
    st.error("⚠️ IA : fuite détectée !")
    # Vérification automatique des plumes Carbon Mapper
    plumes = get_ch4_plumes_carbonmapper(latitude, longitude)
    st.session_state["plumes"] = plumes

    if len(plumes) > 0:
        st.error(f"⚠️ {len(plumes)} plume(s) détectée(s) par Carbon Mapper !")
        for plume in plumes:
            st.write(f"- Emission {plume['emission']} kg/h à ({plume['lat']:.4f},{plume['lon']:.4f})")
    else:
        st.warning("⚠️ IA détecte une fuite, mais aucune plume Carbon Mapper confirmée")
    # ================= Tableau =================
    df_day = pd.DataFrame([{
        "Date image": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ (ppb)": round(ch4, 2),
        "Risque": risk,
        "Action HSE": action
    }])

    st.table(df_day)

# ================= SECTION F : PDF =================
def generate_professional_pdf(site_name, date_img, ch4_value, action, responsable="HSE Manager"):
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
    story.append(Paragraph(f"<b>Responsable action :</b> {responsable}", styles["Normal"]))
    story.append(Spacer(1,12))
    story.append(Paragraph(
        "Ce rapport présente la surveillance du méthane (CH₄) sur le site, "
        "les valeurs mesurées, et les actions correctives recommandées. "
        "Les seuils HSE sont : Élevé ≥1850 ppb, Critique ≥1900 ppb.",
        styles["Normal"]
    ))
    story.append(Spacer(1,12))

    data_table = [
        ["Paramètre","Valeur"],
        ["CH₄ mesuré (ppb)", f"{ch4_value:.1f}"],
        ["Anomalie détectée", "Oui" if ch4_value>=1900 else "Non"],
        ["Action corrective", action]
    ]
    t = Table(data_table, hAlign="LEFT", colWidths=[200,250])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.darkblue),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
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

st.markdown("## 📄 Télécharger PDF Professionnel")
if st.button("Générer PDF Professionnel"):
    if "ch4" not in st.session_state:
        st.warning("Lancez d'abord l'analyse du jour pour générer le PDF")
    else:
        pdf_buffer = generate_professional_pdf(
            st.session_state["site_name"],
            st.session_state["date_img"],
            st.session_state["ch4"],
            st.session_state["action"]
        )
        st.download_button(
            "⬇️ Télécharger le PDF Professionnel",
            pdf_buffer,
            f"Rapport_HSE_CH4_{st.session_state['site_name']}_{st.session_state['date_img']}.pdf",
            "application/pdf"
        )
