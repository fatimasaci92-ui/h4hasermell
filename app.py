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

# ------------------------ CONFIG ------------------------
st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")

# ------------------------ 1) Informations site ------------------------
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

latitude = st.number_input("Latitude du site", value=32.93)
longitude = st.number_input("Longitude du site", value=3.3)
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ------------------------ 2) Chemins fichiers ------------------------
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2025)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2025)}
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")

# ------------------------ 3) Vérification contenu dossier ------------------------
st.subheader("Contenu des sous-dossiers")
st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
st.write("CSV 2020-2024 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ------------------------ 4) Charger CSV ------------------------
df_global = pd.read_csv(csv_global) if os.path.exists(csv_global) else pd.DataFrame()
df_annual = pd.read_csv(csv_annual) if os.path.exists(csv_annual) else pd.DataFrame()
df_monthly = pd.read_csv(csv_monthly) if os.path.exists(csv_monthly) else pd.DataFrame()

st.write("Aperçu CSV annuel :")
if not df_annual.empty:
    st.write(df_annual.head())
else:
    st.info("CSV annuel introuvable ou vide.")

# ------------------------ 5) Graphique évolution CH4 ------------------------
st.markdown("## Évolution CH₄ (2020-2024)")
if not df_annual.empty and 'year' in df_annual.columns and 'CH4_mean' in df_annual.columns:
    years = df_annual['year']
    ch4_values = df_annual['CH4_mean']
    fig, ax = plt.subplots(figsize=(8,4))
    ax.plot(years, ch4_values, marker='o')
    ax.set_title(f"Évolution CH₄ – {site_name}")
    ax.set_xlabel("Année")
    ax.set_ylabel("CH₄ (ppb)")
    ax.grid(True)
    st.pyplot(fig)
else:
    st.info("Pas de données annuelles pour graphique.")

# ------------------------ 6) Cartes affichées seulement après clic ------------------------
st.markdown("## 🗺️ Afficher les cartes CH₄ par année")

year_choice = st.selectbox("Choisir l'année", [2020, 2021, 2022, 2023, 2024])

if st.button("📌 Afficher les cartes de l'année sélectionnée"):
    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"CH₄ moyen {year_choice}")
        if os.path.exists(mean_files[year_choice]):
            with rasterio.open(mean_files[year_choice]) as src:
                arr = src.read(1)
            arr[arr <= 0] = np.nan
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.imshow(arr, cmap='viridis')
            ax.set_title(f"CH₄ moyen {year_choice}")
            ax.axis('off')
            st.pyplot(fig)
        else:
            st.warning("Fichier CH₄ moyen introuvable.")

    with col2:
        st.subheader(f"Anomalie CH₄ {year_choice}")
        if os.path.exists(anomaly_files[year_choice]):
            with rasterio.open(anomaly_files[year_choice]) as src:
                arr = src.read(1)
            arr[arr == 0] = np.nan
            fig, ax = plt.subplots(figsize=(6, 5))
            ax.imshow(arr, cmap='coolwarm')
            ax.set_title(f"Anomalie CH₄ {year_choice}")
            ax.axis('off')
            st.pyplot(fig)
        else:
            st.warning("Fichier anomalie CH₄ introuvable.")


# ------------------------ 7) Analyse HSE automatique après clic ------------------------
st.markdown("## 🔎 Analyse HSE pour l'année sélectionnée")

if st.button("📘 Afficher l'analyse HSE"):
    if not df_annual.empty and year_choice in df_annual['year'].values:

        mean_ch4_year = float(df_annual[df_annual['year'] == year_choice]['CH4_mean'].values[0])

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

        st.success(f"Année analysée : {year_choice}")
        st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
        st.write(f"**Risque HSE :** {risk}")
        st.write(f"**Action recommandée :** {action}")

        # HAZOP
        df_hazop = hazop_analysis(mean_ch4_year)
        st.markdown("### 📊 Tableau HAZOP")
        st.table(df_hazop)

    else:
        st.warning("Les données CH₄ pour cette année sont manquantes.")

# ------------------------ 7bis) Analyse HAZOP ------------------------
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

st.markdown("## Analyse HAZOP automatique")
df_hazop = None
if mean_ch4_year is not None:
    df_hazop = hazop_analysis(mean_ch4_year)
    st.table(df_hazop)
else:
    st.info("Impossible de générer HAZOP : données manquantes pour cette année.")
# ------------------------ 9+10) Analyse CH4 du jour + tableau ------------------------
st.markdown("## 🔍 Analyse CH₄ du jour avec tableau")

if st.button("Analyser aujourd'hui"):
    # Simulation récupération CH4 du jour
    ch4_today = 1935  # ppb, tu peux changer selon les données réelles
    threshold = 1900  # seuil critique

    # Message simple
    st.write(f"**CH₄ du jour :** {ch4_today} ppb")
    
    if ch4_today > threshold:
        st.error("⚠️ Anomalie détectée : niveau CH₄ critique !")
    elif ch4_today > threshold - 50:
        st.warning("⚠️ CH₄ élevé, surveillance recommandée.")
    else:
        st.success("CH₄ normal, aucune anomalie détectée.")
    
    # Tableau
    anomalies_today = pd.DataFrame({
        "Date": [datetime.now().strftime("%d/%m/%Y")],
        "Site": [site_name],
        "CH4 (ppb)": [ch4_today],
        "Anomalie": ["Oui" if ch4_today > threshold else "Non"],
        "Action HSE": [
            "Alerter, sécuriser la zone et stopper opérations" if ch4_today > threshold 
            else "Surveillance continue"
        ]
    })
    st.table(anomalies_today)
import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def generate_pdf(report_date, site_name, ch4_value, anomaly_flag, action_hse, latitude, longitude):
    pdf_path = f"rapport_CH4_{report_date}.pdf"

    # Styles
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    normal_style = styles["BodyText"]

    doc = SimpleDocTemplate(pdf_path)
    story = []

    # ---- TITRE ----
    story.append(Paragraph("Rapport d’Analyse Quotidienne – Méthane (CH₄)", title_style))
    story.append(Spacer(1, 12))

    # ---- CONTEXTE ----
    story.append(Paragraph(
        f"Date du rapport : <b>{report_date}</b><br/>"
        f"Heure de génération : <b>{datetime.datetime.now().strftime('%H:%M:%S')}</b><br/><br/>"
        f"Site analysé : <b>{site_name}</b><br/>"
        f"Localisation : Latitude <b>{latitude}</b>, Longitude <b>{longitude}</b><br/>",
        normal_style
    ))
    story.append(Spacer(1, 12))

    # ---- DESCRIPTION ----
    story.append(Paragraph(
        "Ce rapport présente les concentrations de méthane observées aujourd'hui sur le site "
        "ainsi que l’évaluation automatique des anomalies. Le méthane (CH₄) est un gaz inflammable "
        "dont la présence à forte concentration peut indiquer une fuite, une mauvaise ventilation "
        "ou une activité industrielle anormale.",
        normal_style
    ))
    story.append(Spacer(1, 12))

    # ---- TABLEAU ----
    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration CH₄ (ppb)", ch4_value],
        ["Anomalie détectée", "Oui" if anomaly_flag else "Non"],
        ["Action recommandée HSE", action_hse],
    ]

    table = Table(table_data, colWidths=[180, 260])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#003366")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.8, colors.grey)
    ]))

    story.append(table)
    story.append(Spacer(1, 18))

    # ---- INTERPRÉTATION ----
    interpretation = (
        "L’analyse indique une concentration anormale de méthane, ce qui peut être dû à :<br/>"
        "- Une fuite de canalisation<br/>"
        "- Une activité industrielle anormale<br/>"
        "- Une combustion incomplète<br/>"
        "- Une émission diffuse ou ponctuelle non contrôlée<br/><br/>"
        "Les équipes HSE doivent intervenir immédiatement pour localiser précisément la source, "
        "sécuriser la zone et appliquer les mesures correctives nécessaires."
    )

    story.append(Paragraph(interpretation, normal_style))

    # ---- GÉNÉRATION DU PDF ----
    doc.build(story)

    return pdf_path



# ------------------------ 8) Génération PDF professionnel ------------------------
def generate_pdf_bytes_professional(site_name, latitude, longitude, year, mean_ch4, risk_level, actions_reco, hazop_df):
    buffer = io.BytesIO()
    file_name = f"Rapport_HSE_CH4_{site_name}_{year}.pdf"
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=file_name)
    styles = getSampleStyleSheet()
    story = []

    # TITRE
    title = "<para align='center'><b><font size=18>RAPPORT TECHNIQUE HSE – SURVEILLANCE MÉTHANE</font></b></para>"
    story.append(Paragraph(title, styles["Title"]))
    story.append(Spacer(1, 20))

    # MÉTA-DONNÉES
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    meta = f"""
    <b>Date du rapport :</b> {date_str}<br/>
    <b>Site analysé :</b> {site_name}<br/>
    <b>Latitude :</b> {latitude}<br/>
    <b>Longitude :</b> {longitude}<br/>
    <b>Année analysée :</b> {year}<br/>
    """
    story.append(Paragraph(meta, styles["Normal"]))
    story.append(Spacer(1, 20))

    # TABLEAU TECHNIQUE CH4
    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration moyenne CH₄", f"{mean_ch4:.2f} ppb"],
        ["Niveau de risque HSE", risk_level]
    ]
    table = Table(table_data, colWidths=[200, 250])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E3A8A")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#F3F4F6")),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(table)
    story.append(Spacer(1, 25))

    # RISQUE HSE
    risk_text = f"<b>Analyse du risque :</b><br/><br/>Le niveau de risque détecté en <b>{year}</b> est : <b>{risk_level}</b>.<br/><br/>Cette analyse suit les référentiels : API, OSHA, ISO 45001."
    story.append(Paragraph(risk_text, styles["Normal"]))
    story.append(Spacer(1, 25))

    # ACTIONS RECOMMANDÉES
    actions_text = f"<b>Actions recommandées :</b><br/><br/>{actions_reco}<br/><br/>"
    story.append(Paragraph(actions_text, styles["Normal"]))
    story.append(Spacer(1, 25))

    # TABLEAU HAZOP
    if hazop_df is not None:
        hazop_data = [list(hazop_df.columns)] + hazop_df.values.tolist()
        hazop_table = Table(hazop_data, colWidths=[100,100,150,150,150])
        hazop_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E40AF")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 10),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor("#F3F4F6")),
            ('GRID', (0,0), (-1,-1), 1, colors.black),
        ]))
        story.append(Paragraph("<b>Tableau HAZOP :</b>", styles["Normal"]))
        story.append(Spacer(1,10))
        story.append(hazop_table)
        story.append(Spacer(1, 25))

    # FOOTER
    footer = "<para align='center'><font size=10 color='#6B7280'>Rapport généré automatiquement — Système HSE CH₄<br/>Conforme aux bonnes pratiques ISO 45001</font></para>"
    story.append(Paragraph(footer, styles["Normal"]))

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ---------------------- BOUTON PDF PROFESSIONNEL ----------------------
st.markdown("## 📄 Générer le rapport HSE PDF professionnel")
if mean_ch4_year is not None:
    if st.button("Générer le rapport PDF HSE professionnel"):
        pdf_bytes = generate_pdf_bytes_professional(
            site_name=site_name,
            latitude=latitude,
            longitude=longitude,
            year=year_choice,
            mean_ch4=mean_ch4_year,
            risk_level=risk,
            actions_reco=action,
            hazop_df=df_hazop
        )
        st.download_button(
            label="⬇ Télécharger le rapport PDF professionnel",
            data=pdf_bytes,
            file_name=f"Rapport_HSE_{site_name}_{year_choice}.pdf",
            mime="application/pdf"
        )
else:
    st.info("Impossible de générer le PDF : données manquantes pour cette année.")
