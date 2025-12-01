import streamlit as st
import pandas as pd
import numpy as np
import rasterio
import matplotlib.pyplot as plt
import os
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime

st.set_page_config(page_title="Surveillance CH4 – HSE", layout="wide")

# ------------------------
# 1) Informations site
# ------------------------
st.title("Surveillance du Méthane – HSE")
st.markdown("## Dashboard interactif CH₄ + HSE")

latitude = st.number_input("Latitude du site", value=32.93)
longitude = st.number_input("Longitude du site", value=3.3)
site_name = st.text_input("Nom du site", value="Hassi R'mel")
site_geom = (latitude, longitude)

# ------------------------
# 2) Chemins fichiers
# ------------------------
DATA_DIR = "data"
MEAN_DIR = os.path.join(DATA_DIR, "Moyenne CH4")
ANOMALY_DIR = os.path.join(DATA_DIR, "anomaly CH4")
CSV_DIR = os.path.join(DATA_DIR, "2020 2024")

mean_files = {year: os.path.join(MEAN_DIR, f"CH4_mean_{year}.tif") for year in range(2020, 2025)}
anomaly_files = {year: os.path.join(ANOMALY_DIR, f"CH4_anomaly_{year}.tif") for year in range(2020, 2025)}
csv_global = os.path.join(CSV_DIR, "CH4_HassiRmel_2020_2024.csv")
csv_annual = os.path.join(CSV_DIR, "CH4_HassiRmel_annual_2020_2024.csv")
csv_monthly = os.path.join(CSV_DIR, "CH4_HassiRmel_monthly_2020_2024.csv")

# ------------------------
# 3) Vérification contenu dossier
# ------------------------
st.subheader("Contenu des sous-dossiers")
st.write("Moyenne CH4 :", os.listdir(MEAN_DIR) if os.path.exists(MEAN_DIR) else "Introuvable")
st.write("Anomalies CH4 :", os.listdir(ANOMALY_DIR) if os.path.exists(ANOMALY_DIR) else "Introuvable")
st.write("CSV 2020-2024 :", os.listdir(CSV_DIR) if os.path.exists(CSV_DIR) else "Introuvable")

# ------------------------
# 4) Charger CSV
# ------------------------
df_global = pd.read_csv(csv_global) if os.path.exists(csv_global) else pd.DataFrame()
df_annual = pd.read_csv(csv_annual) if os.path.exists(csv_annual) else pd.DataFrame()
df_monthly = pd.read_csv(csv_monthly) if os.path.exists(csv_monthly) else pd.DataFrame()

st.write("Aperçu CSV annuel :")
if not df_annual.empty:
    st.write(df_annual.head())
else:
    st.info("CSV annuel introuvable ou vide.")

# ------------------------
# 5) Graphique évolution CH4
# ------------------------
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

# ------------------------
# 6) Affichage cartes par année
# ------------------------
st.markdown("## Cartes Moyennes et Anomalies CH₄")
year_choice = st.selectbox("Choisir l'année", [2020,2021,2022,2023,2024])

col1, col2 = st.columns(2)

with col1:
    st.subheader(f"CH₄ moyen {year_choice}")
    if os.path.exists(mean_files[year_choice]):
        with rasterio.open(mean_files[year_choice]) as src:
            arr = src.read(1)
        arr[arr <= 0] = np.nan
        fig, ax = plt.subplots(figsize=(6,5))
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
        fig, ax = plt.subplots(figsize=(6,5))
        ax.imshow(arr, cmap='coolwarm')
        ax.set_title(f"Anomalie CH₄ {year_choice}")
        ax.axis('off')
        st.pyplot(fig)
    else:
        st.warning("Fichier anomalie CH₄ introuvable.")

# ------------------------
# 7) Analyse HSE automatique
# ------------------------
st.markdown("## Analyse HSE automatique")

mean_ch4_year = None
risk = None
action = None

if not df_annual.empty and 'year' in df_annual.columns and 'CH4_mean' in df_annual.columns:
    if year_choice in df_annual['year'].values:
        mean_ch4_year = float(df_annual[df_annual['year']==year_choice]['CH4_mean'].values[0])
        # Niveau de risque HSE
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

        st.write(f"**Année :** {year_choice}")
        st.write(f"**Moyenne CH₄ :** {mean_ch4_year:.2f} ppb")
        st.write(f"**Niveau de risque HSE :** {risk}")
        st.write(f"**Actions recommandées :** {action}")
    else:
        st.info("Pas de données CH₄ pour cette année.")
else:
    st.info("Pas assez de données HSE pour cette année.")

# ------------------------
# 8) Export PDF HSE
# ------------------------
st.markdown("## Générer le rapport HSE complet")

def generate_pdf_bytes(year, mean_ch4, risk, action):
    import io
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from datetime import datetime

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Rapport_HSE_{year}.pdf"
    )

    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    story = []

    # ---------------------- TITRE ----------------------
    title = f"""
    <para align='center'>
    <b><font size=18>RAPPORT TECHNIQUE HSE – SURVEILLANCE MÉTHANE</font></b><br/><br/>
    <font size=14>Site : {site_name}</font><br/>
    <font size=12>Année : {year}</font><br/>
    <font size=10>Date de génération : {datetime.now().strftime('%d/%m/%Y %H:%M')}</font>
    </para>
    """
    story.append(Paragraph(title, style_normal))
    story.append(Spacer(1, 20))

    # ---------------------- TABLEAU ----------------------
    table_data = [
        ["Paramètre", "Valeur"],
        ["Concentration moyenne CH₄", f"{mean_ch4:.2f} ppb"],
        ["Niveau de risque HSE", risk],
        ["Actions recommandées", action]
    ]

    table = Table(table_data, colWidths=[200, 300])
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
    story.append(Spacer(1, 20))

    # ---------------------- ANALYSE RISQUE ----------------------
    risk_text = f"""
    <b>Analyse du risque :</b><br/>
    Le niveau de risque détecté est : <b>{risk}</b>.<br/><br/>
    Une concentration élevée de méthane peut entraîner :<br/>
    • Risque d’explosion<br/>
    • Asphyxie en zone confinée<br/>
    • Instabilité opérationnelle<br/>
    • Incendie continu<br/><br/>
    Références : API, OSHA, ISO 45001
    """
    story.append(Paragraph(risk_text, style_normal))
    story.append(Spacer(1, 20))

    # ---------------------- FOOTER ----------------------
    footer = f"""
    <para align='center'>
    <font size=10 color="#555555">
    Rapport généré automatiquement — Système HSE CH₄<br/>
    Site : {site_name} — Année : {year}
    </font>
    </para>
    """
    story.append(Paragraph(footer, style_normal))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes


if mean_ch4_year is not None:
    if st.button("📄 Générer le PDF HSE"):
        pdf_bytes = generate_pdf_bytes(year_choice, mean_ch4_year, risk, action)
        st.download_button(
            label="Télécharger le rapport HSE PDF",
            data=pdf_bytes,
            file_name=f"Rapport_HSE_{site_name}_{year_choice}.pdf",
            mime="application/pdf"
        )
else:
    st.info("Impossible de générer le PDF : données manquantes pour cette année.")
