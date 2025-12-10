# app_enhanced.py – VERSION AMÉLIORÉE
import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
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
    st.success("✅ Google Earth Engine initialisé")
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

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2020_2025.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")

# ================= SESSION STATE =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= FONCTIONS UTILITAIRES =================
def get_latest_ch4_from_gee(lat, lon):
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

    return float(ch4_ppb) * 1e9, date_img

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

def generate_pdf_bytes_professional(site_name, latitude, longitude, report_date, ch4_value, anomaly_flag, action_hse, hazop_df=None, ch4_history=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Rapport_HSE_{site_name}_{report_date}")
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
    story.append(Spacer(1, 12))

    meta = f"""
    <b>Date :</b> {report_date}<br/>
    <b>Heure :</b> {datetime.now().strftime("%H:%M")}<br/>
    <b>Site :</b> {site_name}<br/>
    <b>Latitude :</b> {latitude}<br/>
    <b>Longitude :</b> {longitude}<br/>
    """
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 12))

    explanation = (
        f"Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté "
        f"sur le site <b>{site_name}</b>. La surveillance du CH₄ permet d'identifier les anomalies, "
        "d'évaluer le niveau de risque HSE et de recommander des actions."
    )
    story.append(Paragraph(explanation, styles["Normal"]))
    story.append(Spacer(1, 12))

    # Tableau résumé
    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration CH₄ (ppb)", f"{ch4_value:.1f}"],
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

    # Graphique CH4
    if ch4_history is not None and len(ch4_history) > 0:
        plt.figure(figsize=(5,3))
        plt.plot(ch4_history['date'], ch4_history['CH4 (ppb)'], marker='o', color='green')
        plt.title("Historique CH₄")
        plt.xlabel("Date")
        plt.ylabel("CH₄ (ppb)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        img_buffer = io.BytesIO()
        plt.savefig(img_buffer, format='PNG')
        plt.close()
        img_buffer.seek(0)
        story.append(Image(img_buffer, width=400, height=200))
        story.append(Spacer(1, 12))

    # HAZOP
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

