# ================= app.py — VERSION FINALE COMPLÈTE =================
# Surveillance CH₄ – HSE | Streamlit + Google Earth Engine

import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os, io, json, tempfile
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
import ee

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH₄ – HSE", layout="wide")
st.title("🛢️ Surveillance du Méthane (CH₄) – HSE")

# ================= SESSION STATE =================
for k in ["ch4", "date_img", "action", "risk"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ================= INITIALISATION GEE =================
try:
    ee_key_json = json.loads(st.secrets["EE_KEY_JSON"])
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(ee_key_json, f)
        key_path = f.name
    credentials = ee.ServiceAccountCredentials(ee_key_json["client_email"], key_path)
    ee.Initialize(credentials)
    os.remove(key_path)
except Exception as e:
    st.error(f"Erreur Google Earth Engine : {e}")
    st.stop()

# ================= PARAMÈTRES SITE =================
latitude = st.number_input("Latitude", value=32.93, format="%.6f")
longitude = st.number_input("Longitude", value=3.30, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= FONCTION GEE =================
def get_latest_ch4_from_gee(lat, lon, days_back=60):
    point = ee.Geometry.Point([lon, lat])
    end = ee.Date(datetime.utcnow().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    col = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
           .filterBounds(point)
           .filterDate(start, end)
           .select("CH4_column_volume_mixing_ratio_dry_air")
           .sort("system:time_start", False))

    size = col.size().getInfo()
    if size == 0:
        return None, None, True

    imgs = col.toList(size)
    for i in range(size):
        img = ee.Image(imgs.get(i))
        date_img = ee.Date(img.get("system:time_start")).format("YYYY-MM-dd").getInfo()
        val = img.reduceRegion(ee.Reducer.mean(), point, 7000, maxPixels=1e9)
        v = val.get("CH4_column_volume_mixing_ratio_dry_air")
        try:
            v = v.getInfo()
        except:
            v = None
        if v:
            return float(v) * 1000, date_img, date_img != datetime.utcnow().strftime("%Y-%m-%d")
    return None, None, True

# ================= ANALYSE DU JOUR =================
st.markdown("## 🔍 Analyse CH₄ du jour")

if st.button("Analyser CH₄ du jour"):
    ch4, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)
    if ch4 is None:
        st.error("Aucune image satellite disponible")
    else:
        st.session_state.ch4 = ch4
        st.session_state.date_img = date_img

        if ch4 >= 1900:
            risk = "Critique"
            action = "Arrêt immédiat + alerte HSE"
            st.error(f"⚠️ {risk} — {ch4:.1f} ppb")
        elif ch4 >= 1850:
            risk = "Élevé"
            action = "Inspection urgente"
            st.warning(f"⚠️ {risk} — {ch4:.1f} ppb")
        else:
            risk = "Normal"
            action = "Surveillance continue"
            st.success(f"✅ {risk} — {ch4:.1f} ppb")

        st.session_state.action = action
        st.session_state.risk = risk

        st.table(pd.DataFrame([{
            "Site": site_name,
            "Date image": date_img,
            "CH₄ (ppb)": round(ch4, 2),
            "Risque": risk,
            "Action HSE": action
        }]))

# ================= PDF HSE =================
st.markdown("## 📄 Rapport PDF HSE")

if st.button("Générer PDF du jour"):
    if st.session_state.ch4 is None:
        st.warning("Lance d'abord l'analyse du jour")
    else:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []

        if os.path.exists("logo.png"):
            story.append(Image("logo.png", width=120, height=50))
            story.append(Spacer(1, 10))

        story.append(Paragraph("<b>Rapport HSE – Surveillance CH₄</b>", styles["Title"]))
        story.append(Spacer(1, 12))

        table = Table([
            ["Site", site_name],
            ["Date image", st.session_state.date_img],
            ["CH₄ (ppb)", f"{st.session_state.ch4:.1f}"],
            ["Risque", st.session_state.risk],
            ["Action HSE", st.session_state.action]
        ])

        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 1, colors.black),
            ('BACKGROUND', (0,0), (0,-1), colors.lightgrey)
        ]))

        story.append(table)
        story.append(Spacer(1, 20))
        story.append(Paragraph("<b>Seuils HSE :</b><br/>Normal < 1850 ppb<br/>Élevé 1850–1900 ppb<br/>Critique > 1900 ppb", styles["Normal"]))

        doc.build(story)

        st.download_button(
            "⬇️ Télécharger le PDF",
            buffer.getvalue(),
            f"Rapport_CH4_{site_name}_{st.session_state.date_img}.pdf",
            "application/pdf"
        )

# ================= AGENT IA =================
st.markdown("## 🤖 Agent IA HSE")

question = st.chat_input("Pose une question sur l'analyse CH₄ ou HSE")

if question:
    response = (
        f"Analyse du site {site_name} : \
        CH₄ = {st.session_state.ch4} ppb. \
        Niveau de risque : {st.session_state.risk}. \
        Action recommandée : {st.session_state.action}."
    )
    st.chat_message("assistant").write(response)

# ================= FIN =================
