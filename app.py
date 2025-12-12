# app.py – VERSION COMPLÈTE ET INTÉGRÉE
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
    ee_key_json_str = st.secrets["EE_KEY_JSON"]  # JSON du service account
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
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_annual_2020_2025.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")
csv_daily = os.path.join(CSV_DIR, "CH4_daily_2025.csv")

# ================= SESSION STATE =================
if 'analysis_today' not in st.session_state:
    st.session_state['analysis_today'] = None

# ================= FONCTIONS UTILITAIRES =================
def get_latest_ch4_from_gee(latitude, longitude, days_back=30):
    """Retourne la DERNIÈRE image disponible dans GEE (même si ce n'est pas aujourd'hui)."""

    point = ee.Geometry.Point([longitude, latitude])

    # Filtrer images sur 30 jours
    end = ee.Date(datetime.now().strftime("%Y-%m-%d"))
    start = end.advance(-days_back, "day")

    collection = (
        ee.ImageCollection("COPERNICUS/S5P/OFFL/L3_CH4")
        .filterBounds(point)
        .filterDate(start, end)
        .select("CH4_column_volume_mixing_ratio_dry_air")
        .sort("system:time_start", False)  # tri décroissant → dernier passage
    )

    img = collection.first()
    if img is None:
        return None, None, True  # pas de données du tout

    # Valeur CH4 au point
    value = img.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=1000
    ).get("CH4_column_volume_mixing_ratio_dry_air")

    if value.getInfo() is None:
        return None, None, True

    ch4_ppb = float(value.getInfo()) * 1e9  # convertir mol/mol → ppb

    # Date réelle de l'image
    date_img = ee.Date(img.get("system:time_start")).format("yyyy-MM-dd").getInfo()

    return ch4_ppb, date_img, False

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

    ch4_ppb = float(ch4_ppb) * 1e9
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
        "Ce rapport présente l'analyse automatisée du niveau de méthane (CH₄) détecté "
        f"sur le site <b>{site_name}</b>. La surveillance du CH₄ permet d'identifier les anomalies, "
        "d'évaluer le niveau de risque HSE et de recommander des actions."
    )
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

    # Graphique historique CH4 si disponible
    if ch4_history is not None and not ch4_history.empty:
        fig, ax = plt.subplots(figsize=(6,3))
        ax.plot(ch4_history['date'], ch4_history['CH4 (ppb)'], marker='o')
        ax.set_title("Historique CH₄")
        ax.set_xlabel("Date")
        ax.set_ylabel("CH₄ (ppb)")
        ax.tick_params(axis='x', rotation=45)
        plt.tight_layout()

        img_buf = io.BytesIO()
        fig.savefig(img_buf, format='PNG')
        plt.close(fig)
        img_buf.seek(0)
        story.append(Image(img_buf, width=450, height=200))
        story.append(Spacer(1,12))

    footer = "<para align='center'><font size=9 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄</font></para>"
    story.append(Paragraph(footer, styles["Normal"]))

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ===================== SECTION A: Contenu des sous-dossiers =====================
st.markdown("## 📁 Contenu des sous-dossiers")
if st.button("Afficher le contenu des sous-dossiers"):
    st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
    st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
    st.write("CSV 2020-2024 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ===================== SECTION B: Aperçu CSV annuel =====================
st.markdown("## 📑 Aperçu CSV annuel")
if st.button("Afficher aperçu CSV annuel"):
    if os.path.exists(csv_annual):
        try:
            df_annual = pd.read_csv(csv_annual)
            st.write(df_annual.head())
        except Exception as e:
            st.error(f"Erreur lecture CSV annuel: {e}")
    else:
        st.warning("CSV annuel introuvable.")

# ===================== SECTION C: Cartes par année =====================
st.markdown("## 🗺️ Cartes Moyenne & Anomalie par année")
year_choice = st.selectbox("Choisir l'année", [2020,2021,2022,2023,2024,2025])
if st.button("Afficher les cartes de l'année sélectionnée"):
    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"CH₄ moyen {year_choice}")
        mean_path = mean_files.get(year_choice)
        if mean_path and os.path.exists(mean_path):
            try:
                with rasterio.open(mean_path) as src:
                    arr = src.read(1)
                arr[arr <= 0] = np.nan
                fig, ax = plt.subplots(figsize=(6,5))
                ax.imshow(arr, cmap='viridis')
                ax.set_title(f"CH₄ moyen {year_choice}")
                ax.axis('off')
                st.pyplot(fig)
            except Exception as e:
                st.error(f"Erreur affichage CH4 mean: {e}")
        else:
            st.warning("Fichier CH₄ moyen introuvable.")

    with col2:
        st.subheader(f"Anomalie CH₄ {year_choice}")
        an_path = anomaly_files.get(year_choice)
        if an_path and os.path.exists(an_path):
            try:
                with rasterio.open(an_path) as src:
                    arr2 = src.read(1)
                arr2[arr2 == 0] = np.nan
                fig2, ax2 = plt.subplots(figsize=(6,5))
                ax2.imshow(arr2, cmap='coolwarm')
                ax2.set_title(f"Anomalie CH₄ {year_choice}")
                ax2.axis('off')
                st.pyplot(fig2)
            except Exception as e:
                st.error(f"Erreur affichage anomalie CH4: {e}")
        else:
            st.warning("Fichier anomalie CH₄ introuvable.")

# ===================== SECTION D: Analyse HSE annuelle =====================
st.markdown("## 🔎 Analyse HSE annuelle")
if st.button("Afficher l'analyse HSE pour l'année sélectionnée"):
    if os.path.exists(csv_annual):
        try:
            df_annual_local = pd.read_csv(csv_annual)
            if year_choice in df_annual_local['year'].values:
                mean_ch4_year = float(df_annual_local[df_annual_local['year']==year_choice]['CH4_mean'].values[0])
                if mean_ch4_year < 1800:
                    risk = "Faible"
                    action = "Surveillance continue."
                elif mean_ch4_year < 1850:
                    risk = "Modéré"
                    action = "Vérifier les torches et informer l'équipe HSE."
                elif mean_ch4_year < 1900:
                    risk = "Élevé"
                    action = "Inspection urgente du site et mesures de sécurité immédiates."
                else:
                    risk = "Critique"
                    action = "Alerter la direction, sécuriser la zone, stopper les opérations si nécessaire."

                st.success(f"Année : {year_choice}")
                st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
                st.write(f"**Niveau de risque HSE :** {risk}")
                st.write(f"**Actions recommandées :** {action}")

                df_hazop_local = hazop_analysis(mean_ch4_year)
                st.markdown("### Tableau HAZOP")
                st.table(df_hazop_local)
            else:
                st.warning("Pas de données CH₄ pour cette année dans CSV annuel.")
        except Exception as e:
            st.error(f"Erreur lors de la lecture/analyses annuelles: {e}")
    else:
        st.warning("CSV annuel introuvable.")

# ===================== SECTION E + F: Analyse CH4 du jour et PDF =====================
st.markdown("## 🔍 Analyse CH₄ du jour et génération PDF")
if st.button("Analyser et générer PDF du jour"):

    st.info("Analyse en cours...")

    ch4_history = pd.DataFrame()
    ch4_today = None
    date_now = datetime.now().strftime("%d/%m/%Y %H:%M")

    if os.path.exists(csv_daily):
        try:
            try:
                df_daily_local = pd.read_csv(csv_daily)
            except:
                df_daily_local = pd.read_csv(csv_daily, sep=';')

            if not df_daily_local.empty:
                keywords = ['ch4', 'methane', 'mean', 'value', 'ppb']
                ch4_cols = [c for c in df_daily_local.columns if any(k in c.lower() for k in keywords)]

                if ch4_cols:
                    ch4_col = ch4_cols[0]
                    if 'date' in df_daily_local.columns:
                        ch4_history = df_daily_local[['date', ch4_col]].rename(columns={ch4_col:'CH4 (ppb)'})
                    else:
                        ch4_history = df_daily_local[[ch4_col]].copy()
                        ch4_history['date'] = df_daily_local.index
                        ch4_history = ch4_history[['date', 'CH4 (ppb)']]

                    ch4_today = float(df_daily_local[ch4_col].iloc[-1])
                else:
                    ch4_today = None
        except Exception as e:
            st.warning(f"Erreur lecture CSV daily: {e}")

    if ch4_today is None:
        st.info("Lecture valeur CH₄ depuis Google Earth Engine...")
        ch4_today, date_img = get_latest_ch4_from_gee(latitude, longitude)
        if ch4_today is None:
            st.error("⚠️ Pas de donnée TROPOMI disponible. Valeur simulée utilisée.")
            ch4_today = 1935.0
            date_img = date_now.split()[0]

    threshold = 1900.0
    if ch4_today > threshold:
        action_hse = "Alerter, sécuriser la zone et stopper opérations"
    elif ch4_today > threshold - 50:
        action_hse = "Surveillance renforcée et vérification des torches"
    else:
        action_hse = "Surveillance continue"

    st.session_state['analysis_today'] = {
        "date": date_now,
        "ch4": ch4_today,
        "anomaly": ch4_today > threshold,
        "action": action_hse,
        "threshold": threshold,
        "history": ch4_history
    }

    st.write(f"**CH₄ du jour :** {ch4_today:.1f} ppb  ({date_now})")
    if ch4_today > threshold:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4_today > threshold - 50:
        st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
    else:
        st.success("CH₄ normal, aucune anomalie détectée.")

    anomalies_today_df = pd.DataFrame([{
        "Date": date_now.split()[0],
        "Heure": date_now.split()[1],
        "Site": site_name,
        "Latitude": latitude,
        "Longitude": longitude,
        "CH4 (ppb)": ch4_today,
        "Anomalie": "Oui" if ch4_today > threshold else "Non",
        "Action HSE": action_hse
    }])
    st.table(anomalies_today_df)

    pdf_bytes = generate_pdf_bytes_professional(
        site_name=site_name,
        latitude=latitude,
        longitude=longitude,
        report_date=date_now.split()[0],
        ch4_value=ch4_today,
        anomaly_flag=(ch4_today > threshold),
        action_hse=action_hse,
        hazop_df=hazop_analysis(ch4_today),
        ch4_history=ch4_history
    )

    st.download_button(
        label="⬇ Télécharger le rapport PDF du jour",
        data=pdf_bytes,
        file_name=f"Rapport_HSE_CH4_{site_name}_{date_now.split()[0]}.pdf",
        mime="application/pdf"
    )

# ===================== SECTION G: PDF annuel =====================
st.markdown("## 📄 Génération PDF annuel")
if st.button("Générer PDF annuel"):
    if os.path.exists(csv_annual):
        try:
            df_annual_local = pd.read_csv(csv_annual)
            # Sommaire annuel CH4
            pdf_bytes_annuel = generate_pdf_bytes_professional(
                site_name=site_name,
                latitude=latitude,
                longitude=longitude,
                report_date=datetime.now().strftime("%d/%m/%Y"),
                ch4_value=df_annual_local['CH4_mean'].mean(),
                anomaly_flag=df_annual_local['CH4_mean'].max() > 1900,
                action_hse="Consulter les actions HSE annuelles",
                hazop_df=None,
                ch4_history=df_annual_local.rename(columns={"CH4_mean":"CH4 (ppb)","year":"date"})[['date','CH4 (ppb)']]
            )
            st.download_button(
                label="⬇ Télécharger le rapport PDF annuel",
                data=pdf_bytes_annuel,
                file_name=f"Rapport_HSE_CH4_Annuel_{datetime.now().strftime('%Y-%m-%d')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"Erreur génération PDF annuel: {e}")
    else:
        st.warning("CSV annuel introuvable.")


