# app.py – VERSION FINALE + ANALYSE DU JOUR + HAZOP + PDF

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

# ================= CONFIG =================
st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE + HAZOP")

# ================= INFOS SITE =================
latitude = st.number_input("Latitude du site", value=32.93, format="%.6f")
longitude = st.number_input("Longitude du site", value=3.3, format="%.6f")
site_name = st.text_input("Nom du site", value="Hassi R'mel")

# ================= PATHS =================
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2025")
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2025.csv")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}

if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= FONCTIONS =================
def get_latest_ch4_from_gee(lat, lon):
    """Retourne (valeur_CH4_ppb, date_image) de la dernière image TROPOMI disponible"""
    point = ee.Geometry.Point([lon, lat])
    collection = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                  .filterBounds(point)
                  .select("CH4_column_volume_mixing_ratio_dry_air")
                  .sort("system:time_start", False))
    image = collection.first()
    if image is None:
        return None, None

    value = image.reduceRegion(ee.Reducer.mean(), geometry=point, scale=7000).get("CH4_column_volume_mixing_ratio_dry_air")
    ch4_ppb = ee.Number(value).getInfo()
    date_img = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    if ch4_ppb is None:
        return None, date_img
    return float(ch4_ppb)*1e9, date_img

def hazop_analysis(ch4_value):
    data = []
    if ch4_value < 1800:
        data.append(["CH₄","Normal","Pas d’anomalie","Fonctionnement normal","Surveillance continue"])
    elif ch4_value < 1850:
        data.append(["CH₄","Modérément élevé","Torchage possible","Risque faible d’incident","Vérifier torches et informer l'équipe HSE"])
    elif ch4_value < 1900:
        data.append(["CH₄","Élevé","Fuite probable","Risque d’explosion accru","Inspection urgente du site et mesures de sécurité immédiates"])
    else:
        data.append(["CH₄","Critique","Fuite majeure","Risque critique d’explosion/incendie","Alerter direction, sécuriser zone, stopper les opérations si nécessaire"])
    return pd.DataFrame(data, columns=["Paramètre","Déviation","Cause","Conséquence","Action HSE"])

def generate_pdf_bytes_professional(site_name, latitude, longitude, report_date, ch4_value, anomaly_flag, action_hse, hazop_df=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=f"Rapport_HSE_{site_name}_{report_date}")
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("<para align='center'><b><font size=16>RAPPORT HSE – SURVEILLANCE MÉTHANE (CH₄)</font></b></para>", styles["Title"]))
    story.append(Spacer(1,12))
    meta = f"<b>Date :</b> {report_date}<br/><b>Site :</b> {site_name}<br/><b>Latitude :</b> {latitude}<br/><b>Longitude :</b> {longitude}<br/>"
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1,12))

    table_data = [
        ["Paramètre","Valeur"],
        ["Concentration CH₄ (ppb)", f"{ch4_value}"],
        ["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
        ["Action recommandée HSE", action_hse]
    ]
    table = Table(table_data, colWidths=[180,260])
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),colors.HexColor("#0B4C6E")),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('ALIGN',(0,0),(-1,-1),'LEFT'),
        ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
        ('BACKGROUND',(0,1),(-1,-1),colors.whitesmoke),
        ('GRID',(0,0),(-1,-1),0.8,colors.grey)
    ]))
    story.append(table)
    story.append(Spacer(1,16))

    if hazop_df is not None and not hazop_df.empty:
        hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
        hazop_table = Table(hazop_data, colWidths=[100]*len(hazop_df.columns))
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

# ===================== SECTION 1 : Analyse du jour =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
    ch4_today, date_img = get_latest_ch4_from_gee(latitude, longitude)
    
    if ch4_today is None:
        st.warning("⚠️ Pas de donnée TROPOMI pour aujourd'hui, utilisation de la dernière image disponible")
        # On reprend la dernière image disponible
        ch4_today, date_img = get_latest_ch4_from_gee(latitude, longitude)
        if ch4_today is None:
            ch4_today = 0.0
            date_img = "Dernière image disponible"

    threshold = 1900
    action_hse = "Surveillance continue"

    if ch4_today > 0:
        if ch4_today > threshold:
            action_hse = "Alerter, sécuriser zone et stopper opérations"
        elif ch4_today > threshold - 50:
            action_hse = "Surveillance renforcée et vérification torches"

    st.session_state['analysis_today'] = {
        "date": date_img,
        "ch4": ch4_today,
        "anomaly": ch4_today > threshold if ch4_today>0 else False,
        "action": action_hse
    }

    st.write(f"**Date image :** {date_img}")
    st.write(f"**CH₄ :** {ch4_today:.1f} ppb")
    if ch4_today > threshold:
        st.error("⚠️ Niveau CH₄ critique")
    elif ch4_today > threshold-50:
        st.warning("⚠️ CH₄ élevé")
    else:
        st.success("CH₄ normal")
    df_today = pd.DataFrame([{"Date":date_img,"CH4 ppb":ch4_today,"Anomalie":"Oui" if ch4_today>threshold else "Non","Action HSE":action_hse}])
    st.table(df_today)

    # PDF du jour
    if st.button("Générer PDF du jour"):
        analysis = st.session_state.get('analysis_today')
        if analysis and analysis['ch4'] is not None:
            pdf_bytes = generate_pdf_bytes_professional(
                site_name, latitude, longitude,
                analysis['date'], analysis['ch4'],
                analysis['anomaly'], analysis['action'],
                hazop_analysis(analysis['ch4'])
            )
            st.download_button("⬇ Télécharger PDF du jour", data=pdf_bytes,
                               file_name=f"Rapport_CH4_{site_name}_{analysis['date']}.pdf",
                               mime="application/pdf")

# ===================== SECTION 2 : Analyse HAZOP =====================
st.markdown("## ⚠️ Analyse HAZOP")
hazop_ch4 = st.number_input("Entrer valeur CH₄ (ppb) pour HAZOP", min_value=0, max_value=5000, value=1850)
if st.button("Afficher tableau HAZOP"):
    df_hazop = hazop_analysis(hazop_ch4)
    st.table(df_hazop)
    # PDF HAZOP
    pdf_bytes = generate_pdf_bytes_professional(
        site_name, latitude, longitude,
        f"HAZOP_{datetime.now().strftime('%Y%m%d_%H%M')}",
        hazop_ch4, hazop_ch4>1900, "Action HSE recommandée", df_hazop
    )
    st.download_button("⬇ Télécharger PDF HAZOP", data=pdf_bytes,
                       file_name=f"HAZOP_CH4_{site_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                       mime="application/pdf")

# ===================== SECTION 3 : Analyse historique par année =====================
st.markdown("## 📅 Analyse historique CH₄ par année")
available_years = [y for y,p in mean_files.items() if os.path.exists(p)]
if available_years:
    year_choice = st.selectbox("Sélectionner l'année", available_years)
    mean_path = mean_files.get(year_choice)
    an_path = anomaly_files.get(year_choice)
    col1,col2 = st.columns(2)
    with col1:
        st.subheader(f"CH₄ moyen {year_choice}")
        if mean_path and os.path.exists(mean_path):
            with rasterio.open(mean_path) as src:
                arr = src.read(1)
            arr[arr<=0]=np.nan
            fig,ax = plt.subplots(figsize=(6,5))
            ax.imshow(arr,cmap='viridis')
            ax.axis('off')
            st.pyplot(fig)
        else:
            st.warning("Fichier CH₄ moyen introuvable")
    with col2:
        st.subheader(f"Anomalie CH₄ {year_choice}")
        if an_path and os.path.exists(an_path):
            with rasterio.open(an_path) as src:
                arr2 = src.read(1)
            arr2[arr2==0]=np.nan
            fig2,ax2 = plt.subplots(figsize=(6,5))
            ax2.imshow(arr2,cmap='coolwarm')
            ax2.axis('off')
            st.pyplot(fig2)
        else:
            st.warning("Fichier anomalie CH₄ introuvable")
    if st.button(f"Générer PDF CH₄ {year_choice}"):
        if mean_path and os.path.exists(mean_path):
            ch4_value = np.nanmean(arr)
            action_hse = "Surveillance continue"
            pdf_bytes = generate_pdf_bytes_professional(
                site_name, latitude, longitude, str(year_choice),
                ch4_value, ch4_value>1900, action_hse, hazop_analysis(ch4_value)
            )
            st.download_button("⬇ Télécharger PDF", data=pdf_bytes,
                               file_name=f"Rapport_CH4_{site_name}_{year_choice}.pdf",
                               mime="application/pdf")
else:
    st.warning("Aucune année disponible pour analyse")
