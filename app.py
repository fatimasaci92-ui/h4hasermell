# app.py — VERSION COMPLÈTE CORRIGÉE

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import ee
import json
import tempfile

# ================= INITIALISATION GOOGLE EARTH ENGINE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name

    credentials = ee.ServiceAccountCredentials(
        ee_key_json["client_email"],
        key_path
    )
    ee.Initialize(credentials)
    os.remove(key_path)

except Exception as e:
    st.error(f"Erreur GEE : {e}")
    st.stop()

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("Surveillance du Méthane (CH₄) – HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= FONCTION GEE CORRIGÉE =================
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

        ch4_ppb = float(v) * 1000
        today = datetime.utcnow().strftime("%Y-%m-%d")
        no_pass_today = date_img != today

        return ch4_ppb, date_img, no_pass_today

    return None, None, True
# ================= SECTION A : Contenu des dossiers =================
st.markdown("## 📁 Section A — Contenu des données")

DATA_DIR = "data"

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

csv_path = "data/2020 2024/CH4_HassiRmel_2020_2024.csv"

if st.button("Afficher CSV historique"):
    if os.path.exists(csv_path):
        df_hist = pd.read_csv(csv_path)
        st.dataframe(df_hist.head(20))
    else:
        st.warning("CSV historique introuvable")
# ================= SECTION C : Cartes CH₄ =================
st.markdown("## 🗺️ Section C — Carte CH₄ moyenne")

year = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024, 2025])

mean_path = f"data/Moyenne CH4/CH4_mean_{year}.tif"

if st.button("Afficher carte CH₄"):
    if os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
            img = src.read(1)
        img[img <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.imshow(img, cmap="viridis")
        ax.set_title(f"CH₄ moyen {year}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.warning("Carte CH₄ introuvable")
# ================= SECTION D : Analyse HSE annuelle =================
st.markdown("## 🔎 Section D — Analyse HSE annuelle")

csv_annual = "data/2020 2024/CH4_annual_2020_2025.csv"

if st.button("Analyser année sélectionnée"):
    if os.path.exists(csv_annual):
        df_year = pd.read_csv(csv_annual)
        if year in df_year["year"].values:
            val = df_year[df_year["year"] == year]["CH4_mean"].values[0]

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

# =================SZCTION D ANALYSE CH₄ DU JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour (Google Earth Engine)")

if st.button("Analyser CH₄ du jour"):
    st.info("Analyse en cours...")

    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

    if ch4 is None:
        st.error("⚠️ Aucune image satellite disponible sur la période analysée.")
        st.stop()

    if no_pass_today:
        st.error("☁️ Pas de passage satellite aujourd’hui (nuages ou orbite)")
        st.warning(f"➡️ Dernière image disponible sur GEE : **{date_img}**")

    st.success(f"CH₄ : **{ch4:.1f} ppb** (image du {date_img})")

    # Analyse HSE
    if ch4 >= 1900:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
        action = "Alerter, sécuriser la zone et stopper opérations"
    else:
        st.success("CH₄ normal")
        action = "Surveillance continue"

    df = pd.DataFrame([{
        "Date image": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH₄ (ppb)": round(ch4, 2),
        "Anomalie": "Oui" if ch4 >= 1900 else "Non",
        "Action HSE": action
    }])

    st.table(df)
# ================= SECTION F : PDF du jour =================
st.markdown("## 📄 Section F — Rapport PDF du jour")

if st.button("Générer PDF du jour"):
    if "ch4" not in locals():
        st.warning("Lance d'abord l'analyse du jour")
    else:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph("<b>Rapport HSE – CH₄</b>", styles["Title"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Site : {site_name}", styles["Normal"]))
        story.append(Paragraph(f"Date image : {date_img}", styles["Normal"]))
        story.append(Paragraph(f"CH₄ : {ch4:.1f} ppb", styles["Normal"]))
        story.append(Paragraph(f"Action HSE : {action}", styles["Normal"]))

        doc.build(story)

        st.download_button(
            "⬇️ Télécharger le PDF",
            buffer.getvalue(),
            f"Rapport_CH4_{site_name}_{date_img}.pdf",
            "application/pdf"
        )

# ================= FIN =================
