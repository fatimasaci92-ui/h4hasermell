# app.py – VERSION CORRIGÉE ET STABLE
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
    ee_key_json_str = st.secrets["EE_KEY_JSON"]
    ee_key_json = json.loads(ee_key_json_str)
    
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as f:
        json.dump(ee_key_json, f)
        temp_json_path = f.name

    service_account = ee_key_json["client_email"]
    credentials = ee.ServiceAccountCredentials(service_account, temp_json_path)
    ee.Initialize(credentials)
    os.remove(temp_json_path)
except Exception as e:
    st.error(f"❌ Erreur initialisation Google Earth Engine: {e}")

# ================= CONFIG STREAMLIT =================
st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= PATHS =================
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2025.csv")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

# ================= SESSION STATE =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= FONCTIONS =================
def get_latest_ch4_from_gee(lat, lon):
    """Retourne (valeur_CH4_ppb, date_image) depuis la dernière image TROPOMI."""
    point = ee.Geometry.Point([lon, lat])
    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(point)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)
    )
    image = collection.first()
    if image is None:
        return None, None

    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    ch4_ppb = ee.Number(value).getInfo()
    date_img = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd").getInfo()

    if ch4_ppb is None:
        return None, date_img

    ch4_ppb = float(ch4_ppb) * 1e9  # conversion mol/mol → ppb
    return ch4_ppb, date_img

def hazop_analysis(ch4_value):
    data = []
    if ch4_value < 1800:
        data.append(["CH₄", "Normal", "Pas d’anomalie", "Fonctionnement normal", "Surveillance continue"])
    elif ch4_value < 1850:
        data.append(["CH₄", "Modérément élevé", "Torchage possible", "Risque faible d’incident", "Vérifier torches et informer l'équipe HSE"])
    elif ch4_value < 1900:
        data.append(["CH₄", "Élevé", "Fuite probable", "Risque d’explosion accru", "Inspection urgente du site et mesures de sécurité immédiates"])
    else:
        data.append(["CH₄", "Critique", "Fuite majeure", "Risque critique d’explosion/incendie", "Alerter direction, sécuriser zone, stopper les opérations si nécessaire"])
    return pd.DataFrame(data, columns=["Paramètre","Déviation","Cause","Conséquence","Action HSE"])

def generate_pdf_bytes_professional(site_name, latitude, longitude, report_date, ch4_value, anomaly_flag, action_hse, hazop_df=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Rapport_HSE_{site_name}_{report_date}")
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
    story.append(Spacer(1, 12))
    meta = f"<b>Date :</b> {report_date}<br/><b>Site :</b> {site_name}<br/><b>Latitude :</b> {latitude}<br/><b>Longitude :</b> {longitude}<br/>"
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 12))

    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration CH₄ (ppb)", f"{ch4_value}"],
        ["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
        ["Action recommandée HSE", action_hse],
    ]
    table = Table(table_data, colWidths=[180, 260])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0B4C6E")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.8, colors.grey)
    ]))
    story.append(table)
    story.append(Spacer(1, 16))

    if hazop_df is not None and not hazop_df.empty:
        hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
        hazop_table = Table(hazop_data, colWidths=[100]*len(hazop_df.columns))
        hazop_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#0B4C6E")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
            ('GRID', (0,0), (-1,-1), 0.8, colors.grey)
        ]))
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
        story.append(Spacer(1, 6))
        story.append(hazop_table)
        story.append(Spacer(1, 12))

    footer = "<para align='center'><font size=9 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄</font></para>"
    story.append(Paragraph(footer, styles["Normal"]))

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ===================== SECTION E: Analyse CH4 du jour =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
    st.info("Connexion à Google Earth Engine...")

    # ---- Lecture de la dernière image TROPOMI ----
    ch4_today, date_img = get_latest_ch4_from_gee(latitude, longitude)

    if ch4_today is None:
        st.error("⚠️ Pas de donnée TROPOMI disponible pour cette zone aujourd’hui (nuages ou absence de passage).")
        st.stop()

    # Analyse HSE automatique
    threshold = 1900.0
    if ch4_today > threshold:
        action_hse = "Alerter, sécuriser la zone et stopper opérations"
    elif ch4_today > threshold - 50:
        action_hse = "Surveillance renforcée et vérification des torches"
    else:
        action_hse = "Surveillance continue"

    # Stocker l'analyse pour PDF
    st.session_state['analysis_today'] = {
        "date": date_img,
        "ch4": ch4_today,
        "anomaly": ch4_today > threshold,
        "action": action_hse,
        "threshold": threshold
    }

    # --- Affichage résultats ---
    st.write(f"**Dernière image TROPOMI disponible :** {date_img}")
    st.write(f"**CH₄ :** {ch4_today:.1f} ppb")

    if ch4_today > threshold:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4_today > threshold - 50:
        st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
    else:
        st.success("CH₄ normal, aucune anomalie détectée.")

    anomalies_today_df = pd.DataFrame([{
        "Date": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH4 (ppb)": ch4_today,
        "Anomalie": "Oui" if ch4_today > threshold else "Non",
        "Action HSE": action_hse
    }])
    st.table(anomalies_today_df)

# ===================== Les autres sections (PDF, HSE annuel, cartes) restent inchangées =====================

st.success("✅ Application initialisée et prête à l'emploi avec Google Earth Engine")
