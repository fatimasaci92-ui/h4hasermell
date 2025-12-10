# app.py – VERSION COMPLÈTE ET SÉCURISÉE
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

# ================= INITIALISATION GEE =================
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

# ================= CONFIG =================
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
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2025.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")

# ================= SESSION STATE =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= FONCTIONS =================
def get_last_valid_image(lat, lon):
    """Retourne la dernière image TROPOMI avec valeur CH4 valide"""
    point = ee.Geometry.Point([lon, lat])
    collection = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                  .filterBounds(point)
                  .select("CH4_column_volume_mixing_ratio_dry_air")
                  .sort("system:time_start", False))
    # Parcourir la collection jusqu'à trouver valeur valide
    try:
        imgs = collection.getInfo().get('features', [])
    except:
        return 0.0, "Aucune image disponible"

    for img in imgs:
        val = img['properties'].get("CH4_column_volume_mixing_ratio_dry_air")
        if val is not None:
            date_img = img['properties']['system:time_start'][:10]
            ch4_ppb = float(val)*1e9
            return ch4_ppb, date_img
    return 0.0, "Aucune image disponible"

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

    story.append(Paragraph(f"<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
    story.append(Spacer(1,12))
    meta = f"<b>Date :</b> {report_date}<br/><b>Heure :</b> {datetime.now().strftime('%H:%M')}<br/><b>Site :</b> {site_name}<br/><b>Latitude :</b> {latitude}<br/><b>Longitude :</b> {longitude}<br/>"
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1,12))
    explanation = f"Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté sur le site <b>{site_name}</b>."
    story.append(Paragraph(explanation, styles["Normal"]))
    story.append(Spacer(1,12))

    table_data = [["Paramètre","Valeur"],
                  ["Concentration CH₄ (ppb)", f"{ch4_value}"],
                  ["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
                  ["Action recommandée HSE", action_hse]]
    table = Table(table_data,colWidths=[180,260])
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#0B4C6E")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
        ('GRID',(0,0),(-1,-1),0.8,colors.grey)
    ]))
    story.append(table)
    story.append(Spacer(1,12))

    if hazop_df is not None and not hazop_df.empty:
        hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
        hazop_table = Table(hazop_data,colWidths=[100]*len(hazop_df.columns))
        hazop_table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#0B4C6E")),
            ('TEXTCOLOR',(0,0),(-1,0),colors.white),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
            ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
            ('GRID',(0,0),(-1,-1),0.8,colors.grey)
        ]))
        story.append(Spacer(1,12))
        story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
        story.append(Spacer(1,6))
        story.append(hazop_table)
        story.append(Spacer(1,12))

    footer = "<para align='center'><font size=9 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄</font></para>"
    story.append(Paragraph(footer, styles["Normal"]))
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ===================== ANALYSE DU JOUR =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
    ch4_today, date_img = get_last_valid_image(latitude, longitude)

    threshold = 1900
    action_hse = "Surveillance continue"
    if ch4_today > threshold:
        action_hse = "Alerter, sécuriser zone et stopper opérations"
    elif ch4_today > threshold-50:
        action_hse = "Surveillance renforcée et vérification torches"

    st.session_state['analysis_today'] = {
        "date": date_img,
        "ch4": ch4_today,
        "anomaly": ch4_today > threshold if ch4_today>0 else False,
        "action": action_hse
    }

    st.write(f"**Date de l'image utilisée :** {date_img}")
    st.write(f"**CH₄ :** {ch4_today:.1f} ppb")
    if ch4_today > threshold:
        st.error("⚠️ Niveau CH₄ critique")
    elif ch4_today > threshold-50:
        st.warning("⚠️ CH₄ élevé")
    else:
        st.success("CH₄ normal")

    df_today = pd.DataFrame([{"Date":date_img,"CH4 ppb":ch4_today,"Anomalie":"Oui" if ch4_today>threshold else "Non","Action HSE":action_hse}])
    st.table(df_today)

# ===================== PDF DU JOUR =====================
st.markdown("## 📄 Générer rapport PDF du jour")
if st.button("Générer PDF du jour"):
    analysis = st.session_state.get('analysis_today')
    if analysis is None:
        st.warning("Cliquez d'abord sur 'Analyser aujourd'hui'")
    else:
        pdf_bytes = generate_pdf_bytes_professional(
            site_name=site_name,
            latitude=latitude,
            longitude=longitude,
            report_date=analysis['date'],
            ch4_value=analysis['ch4'],
            anomaly_flag=analysis['anomaly'],
            action_hse=analysis['action'],
            hazop_df=hazop_analysis(analysis['ch4'])
        )
        st.download_button(
            label="⬇ Télécharger PDF du jour",
            data=pdf_bytes,
            file_name=f"Rapport_HSE_CH4_{site_name}_{analysis['date']}.pdf",
            mime="application/pdf"
        )
