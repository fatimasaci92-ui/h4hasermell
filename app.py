# app.py – VERSION COMPLÈTE, CORRIGÉE ET FONCTIONNELLE
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

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2026)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2026)}
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2025.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")

# ================= FONCTIONS =================

def get_last_valid_image(lat, lon):
    point = ee.Geometry.Point([lon, lat])
    collection = (ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
                  .filterBounds(point)
                  .select("CH4_column_volume_mixing_ratio_dry_air")
                  .sort("system:time_start", False))

    image = collection.first()
    if image is None:
        return 0.0, None, True

    value = image.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=7000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    try:
        ch4_ppb = float(ee.Number(value).getInfo()) * 1e9
    except:
        ch4_ppb = 0.0

    date_img = ee.Date(image.get("system:time_start")).format("YYYY-MM-dd").getInfo()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    no_pass_today = (date_img != today_str)

    return ch4_ppb, date_img, no_pass_today

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
    meta = f"""
    <b>Date :</b> {report_date}<br/>
    <b>Heure :</b> {datetime.now().strftime("%H:%M")}<br/>
    <b>Site :</b> {site_name}<br/>
    <b>Latitude :</b> {latitude}<br/>
    <b>Longitude :</b> {longitude}<br/>
    """
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 12))
    explanation = f"Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté sur le site <b>{site_name}</b>. La surveillance du CH₄ permet d'identifier les anomalies, d'évaluer le niveau de risque HSE et de recommander des actions."
    story.append(Paragraph(explanation, styles["Normal"]))
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

# ===================== SECTION ANALYSE DU JOUR =====================
st.markdown("## 🔍 Analyse CH₄ du jour")
if st.button("Analyser aujourd'hui"):
    ch4_today, date_img, no_pass_today = get_latest_ch4_from_gee(latitude, longitude)

if no_pass_today:
    st.error(f"⚠️ Pas de passage du satellite aujourd'hui. Dernière image disponible : {date_img}")

    if no_pass_today:
        st.error(f"⚠️ Pas de passage du satellite aujourd'hui. Dernière image disponible : {date_img}")

        # Carte rouge pour signaler absence
        fig, ax = plt.subplots(figsize=(6,5))
        arr = np.ones((10,10,3))
        ax.imshow(arr, cmap=None)
        ax.set_facecolor("red")
        ax.set_title(f"Pas d'image aujourd'hui. Dernière image : {date_img}")
        ax.axis("off")
        st.pyplot(fig)
    else:
        st.success(f"Donnée du jour : {date_img}")

    st.write(f"**CH₄ :** {ch4_today:.1f} ppb")

    # Analyse HSE
    threshold = 1900.0
    if ch4_today > threshold:
        action_hse = "Alerter, sécuriser la zone et stopper opérations"
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4_today > threshold - 50:
        action_hse = "Surveillance renforcée et vérification des torches"
        st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
    else:
        action_hse = "Surveillance continue"
        st.success("CH₄ normal, aucune anomalie détectée.")

    st.session_state['analysis_today'] = {
        "date": date_img,
        "ch4": ch4_today,
        "anomaly": ch4_today>threshold,
        "action": action_hse
    }

    # Tableau
    anomalies_today_df = pd.DataFrame([{
        "Date": date_img,
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH4 (ppb)": ch4_today,
        "Anomalie": "Oui" if ch4_today>threshold else "Non",
        "Action HSE": action_hse
    }])
    st.table(anomalies_today_df)

    # PDF du jour
    pdf_bytes = generate_pdf_bytes_professional(
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        report_date=date_img,
        ch4_value=ch4_today,
        anomaly_flag=ch4_today>threshold,
        action_hse=action_hse,
        hazop_df=hazop_analysis(ch4_today)
    )
    st.download_button(
        label="⬇ Télécharger le rapport PDF du jour",
        data=pdf_bytes,
        file_name=f"Rapport_HSE_CH4_{site_name}_{date_img}.pdf",
        mime="application/pdf"
    )

# ===================== SECTION HISTORIQUE 2020-2025 =====================
st.markdown("## 🗓️ Historique CH₄ (2020 → 2025)")
year_choice = st.selectbox("Sélectionner l'année", list(range(2020,2026)))

col1, col2 = st.columns(2)
with col1:
    st.subheader(f"CH₄ moyen {year_choice}")
    mean_path = mean_files.get(year_choice)
    if mean_path and os.path.exists(mean_path):
        with rasterio.open(mean_path) as src:
            arr = src.read(1)
        arr[arr <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(arr, cmap='viridis')
        ax.axis('off')
        st.pyplot(fig)
    else:
        st.warning("Fichier CH₄ moyen introuvable.")

with col2:
    st.subheader(f"Anomalie CH₄ {year_choice}")
    an_path = anomaly_files.get(year_choice)
    if an_path and os.path.exists(an_path):
        with rasterio.open(an_path) as src:
            arr2 = src.read(1)
        arr2[arr2==0] = np.nan
        fig2, ax2 = plt.subplots(figsize=(6,5))
        ax2.imshow(arr2, cmap='coolwarm')
        ax2.axis('off')
        st.pyplot(fig2)
    else:
        st.warning("Fichier anomalie CH₄ introuvable.")

# PDF annuel
if st.button("Générer PDF professionnel annuel"):
    csv_file = csv_annual
    if os.path.exists(csv_file):
        df_annual_local = pd.read_csv(csv_file)
        if year_choice in df_annual_local['year'].values:
            mean_ch4_year = float(df_annual_local[df_annual_local['year']==year_choice]['CH4_mean'].values[0])
            threshold = 1900
            action = ("Alerter..." if mean_ch4_year>=threshold else
                      "Surveillance renforcée..." if mean_ch4_year>=threshold-50 else
                      "Surveillance continue")
            pdf_bytes = generate_pdf_bytes_professional(
                site_name=site_name,
                latitude=latitude,
                longitude=longitude,
                report_date=str(year_choice),
                ch4_value=mean_ch4_year,
                anomaly_flag=(mean_ch4_year>=threshold),
                action_hse=action,
                hazop_df=hazop_analysis(mean_ch4_year)
            )
            st.download_button(
                label="⬇ Télécharger PDF annuel",
                data=pdf_bytes,
                file_name=f"Rapport_HSE_CH4_{site_name}_{year_choice}.pdf",
                mime="application/pdf"
            )
        else:
            st.warning("Pas de donnée CH₄ pour cette année.")
    else:
        st.warning("CSV annuel introuvable.")
